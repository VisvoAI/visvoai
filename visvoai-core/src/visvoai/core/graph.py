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
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from visvoai.core.state import AgentState

logger = logging.getLogger(__name__)


def _intent_query(messages: Sequence[BaseMessage]) -> str:
    """The retrieval query for this round: the most recent human message's text."""
    for m in reversed(list(messages)):
        if isinstance(m, HumanMessage):
            content = m.content
            return content if isinstance(content, str) else str(content)
    return ""


def build_graph(
    model: BaseChatModel,
    core_tools: List[BaseTool],
    all_tools_map: Dict[str, BaseTool],
    system_prompt: str,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    tool_configs: Optional[Dict[str, Any]] = None,
    lean_prompt: bool = False,
    per_round_retrieve: Optional[Any] = None,
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

        if _use_retrieval:
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

        sys_parts = [system_prompt] if system_prompt else []
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
            return "tools"
        return END

    tools_node = ToolNode(all_tools)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})

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
