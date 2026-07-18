"""
visvoai.core.graph — Core agent graph builder.

Implements the base agent→tools loop used by AgentRuntime. A consumer that needs
a richer graph overrides AgentRuntime.build_graph() to call its own builder
instead of this one.

Graph topology:
    agent → should_continue → tools → (routing fn) → agent
                           ↘ END
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from visvoai.core.state import AgentState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphBuildContext:
    """The build-time inputs handed to AgentRuntime's node/routing override hooks.

    A consumer that overrides `_build_agent_node`, `_build_tools_node`, or
    `_agent_routing` receives this so it can construct its own node bodies from
    the same inputs the core builder uses — without re-implementing build_graph.
    Carries only the generic build inputs; surface-specific state (e.g. plan
    bookkeeping) lives on the runtime subclass itself, not here.
    """
    model: BaseChatModel
    core_tools: List[BaseTool]
    all_tools_map: Dict[str, BaseTool]
    all_tools: List[BaseTool]
    system_prompt: str
    tool_configs: Dict[str, Any] = field(default_factory=dict)
    per_round_retrieve: Optional[Any] = None
    lean_prompt: bool = False
    max_agent_steps: Optional[int] = None

# Default soft step cap. The graph runs `agent` + `tools` as two super-steps per
# tool-calling round, so a turn of N rounds costs ~2N super-steps against
# LangGraph's recursion_limit (set by the caller at invoke/astream time; default
# 25). At this many agent rounds in a turn we force one clean, tool-free finalize
# so the user gets an intentional answer instead of hitting the hard ceiling mid
# tool call. 10 rounds fits comfortably under the default recursion_limit; raise
# both together if you need deeper turns.
DEFAULT_MAX_AGENT_STEPS = 10

_FINALIZE_INSTRUCTION = (
    "[SYSTEM] You have reached the maximum number of tool-using steps for this turn. "
    "Do NOT attempt any further tool calls — they will not be available. Provide your "
    "best final answer now from the information you already have. If the task is "
    "incomplete, summarize what you found and state clearly what remains unresolved."
)


def _intent_query(messages: Sequence[BaseMessage]) -> str:
    """The retrieval query for this round: the most recent human message's text."""
    for m in reversed(list(messages)):
        if isinstance(m, HumanMessage):
            content = m.content
            return content if isinstance(content, str) else str(content)
    return ""


def _rounds_this_turn(messages: Sequence[BaseMessage]) -> int:
    """Number of agent (AIMessage) rounds since the last human message — the turn's depth."""
    n = 0
    for m in reversed(list(messages)):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage):
            n += 1
    return n


def build_graph(
    model: BaseChatModel,
    core_tools: List[BaseTool],
    all_tools_map: Dict[str, BaseTool],
    system_prompt: str,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    tool_configs: Optional[Dict[str, Any]] = None,
    lean_prompt: bool = False,
    per_round_retrieve: Optional[Any] = None,
    max_agent_steps: Optional[int] = DEFAULT_MAX_AGENT_STEPS,
    _runtime: Optional[Any] = None,
):
    """Build the compiled StateGraph for the core agent→tools loop.

    This is the implementation used by AgentRuntime and CLIRuntime. A consumer
    that needs more (approval gates, background tasks, a checkpointer) overrides
    AgentRuntime.build_graph() to call its own builder instead.

    Args:
        model:            LangChain chat model with tool-calling support.
        core_tools:       Tools always bound to the model.
        all_tools_map:    Full tool name→instance map (superset of core_tools).
        system_prompt:    System instructions prepended to every turn.
        checkpointer:     LangGraph checkpointer for multi-turn state (optional).
        tool_configs:     Per-tool config metadata dict (optional, passed to hooks).
        lean_prompt:      If True, skip verbose preamble in system prompt (unused in core).
        per_round_retrieve: Optional retrieve(query) -> [tool_name, ...]. When set,
                          tools in all_tools_map but NOT in core_tools are "deferred"
                          and bound only when retrieved for the current round (on top
                          of the always-bound core_tools). When None, all tools are
                          bound every round (bind-everything, backward compatible).
                          Build one with retrieval.make_per_round_retrieve().
        max_agent_steps:  Soft cap on agent rounds per turn. At this depth the loop
                          forces one tool-free finalize so the user gets a clean
                          answer before LangGraph's recursion_limit fires. Default
                          DEFAULT_MAX_AGENT_STEPS; None disables the guard.
        _runtime:         AgentRuntime instance — hooks are invoked when set.
    """
    tool_configs = tool_configs or {}

    core_tool_objs = list(core_tools) if core_tools else []
    core_tool_names = {t.name for t in core_tool_objs}
    all_tools = list(all_tools_map.values()) if all_tools_map else core_tool_objs

    # Tools not in core_tools are "deferrable" — bound on demand via per_round_retrieve.
    # With no retriever (or no deferrables), binding is identical to bind-everything.
    _deferrable_map = {n: t for n, t in (all_tools_map or {}).items() if n not in core_tool_names}
    _use_retrieval = per_round_retrieve is not None and bool(_deferrable_map)

    # Cache bound models by the frozenset of active tool names so FunctionDeclarations
    # are only rebuilt when the active set actually changes.
    _bound_cache: Dict[frozenset, Any] = {}

    def _bind_for(active_names: Sequence[str]):
        active_deferred = [_deferrable_map[n] for n in (active_names or []) if n in _deferrable_map]
        key = frozenset(core_tool_names | {t.name for t in active_deferred})
        bound = _bound_cache.get(key)
        if bound is None:
            tools = core_tool_objs + active_deferred
            bound = model.bind_tools(tools) if tools else model
            _bound_cache[key] = bound
        return bound

    _bound_all = model.bind_tools(all_tools) if all_tools else model

    async def call_model(state: AgentState):
        messages: Sequence[BaseMessage] = state.get("messages", [])
        sys_parts = [system_prompt] if system_prompt else []

        # Soft step cap: at the ceiling, invoke the UNBOUND model (no tools) so the
        # model cannot call tools, and instruct it to finalize. Invariant guard —
        # without it a misbehaving model loops until the hard recursion_limit.
        force_final = max_agent_steps is not None and _rounds_this_turn(messages) >= max_agent_steps
        if force_final:
            logger.warning("[call_model] soft step cap reached (%s) — forcing finalize", max_agent_steps)
            sys_parts.append(_FINALIZE_INSTRUCTION)
            bound = model
        elif _use_retrieval:
            # active = persistent discoveries + TRANSIENT per-round retrieval on the
            # round's intent (binding-only, not persisted → self-evicting). Non-fatal.
            active = list(state.get("active_mcp_tools") or [])
            try:
                fresh = per_round_retrieve(_intent_query(messages)) or []
                if fresh:
                    active = list(dict.fromkeys([*active, *fresh]))
                    logger.debug("[call_model] per-round retrieval (%d) → %s", len(fresh), fresh)
            except Exception as e:
                logger.warning("[call_model] per-round retrieval failed (non-fatal): %s", e)
            bound = _bind_for(active)
        else:
            bound = _bound_all

        if sys_parts:
            invoke_messages = [SystemMessage(content="\n\n".join(sys_parts))] + list(messages)
        else:
            invoke_messages = list(messages)
        response = await bound.ainvoke(invoke_messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            # Past the cap the finalize round ran UNBOUND, so a well-formed
            # model cannot emit tool calls here. A pathological one (hallucinated
            # calls with no declarations — malformed providers exist) must still
            # END, or it loops to the recursion limit the cap exists to prevent.
            if max_agent_steps is not None and _rounds_this_turn(messages) > max_agent_steps:
                logger.warning("[should_continue] tool calls past the step cap "
                               "(unbound round) — forcing END")
                return END
            return "tools"
        return END

    # Node bodies and agent routing are overridable via runtime hooks. Each hook
    # returns None → use the core default below; or a value → override it. This is
    # what lets a rich consumer (HITL, plan-mode, etc.) supply its own bodies
    # WITHOUT overriding build_graph.
    ctx = GraphBuildContext(
        model=model,
        core_tools=core_tool_objs,
        all_tools_map=all_tools_map or {},
        all_tools=all_tools,
        system_prompt=system_prompt,
        tool_configs=tool_configs,
        per_round_retrieve=per_round_retrieve,
        lean_prompt=lean_prompt,
        max_agent_steps=max_agent_steps,
    )

    agent_node = (_runtime._build_agent_node(ctx) if _runtime is not None else None) or call_model
    tools_node = (_runtime._build_tools_node(ctx) if _runtime is not None else None) or ToolNode(all_tools)
    _agent_routing = _runtime._agent_routing(ctx) if _runtime is not None else None
    if _agent_routing is None:
        _agent_fn, _agent_map = should_continue, {"tools": "tools", END: END}
    else:
        _agent_fn, _agent_map = _agent_routing

    state_cls = _runtime._get_state_class() if _runtime is not None else AgentState
    workflow = StateGraph(state_cls)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", _agent_fn, _agent_map)

    if _runtime is None:
        # Default: always route back to agent after tools.
        workflow.add_edge("tools", "agent")
        _cp = checkpointer
        _interrupt = None
    else:
        _runtime._extend_graph(workflow, tool_configs)
        _tools_fn, _tools_routing_map = _runtime._tools_routing(tool_configs)
        workflow.add_conditional_edges("tools", _tools_fn, _tools_routing_map)
        _cp = _runtime._get_checkpointer(checkpointer)
        _interrupt = _runtime._get_interrupt_nodes()

    return workflow.compile(checkpointer=_cp, interrupt_before=_interrupt)
