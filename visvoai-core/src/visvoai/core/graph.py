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
        per_round_retrieve: Callable for per-round tool retrieval (unused in core).
        _runtime:         AgentRuntime instance — hooks are invoked when set.
    """
    tool_configs = tool_configs or {}
    all_tools = list(all_tools_map.values()) if all_tools_map else list(core_tools)

    _bound_model = model.bind_tools(all_tools) if all_tools else model

    async def call_model(state: AgentState):
        messages: Sequence[BaseMessage] = state.get("messages", [])
        sys_parts = [system_prompt] if system_prompt else []
        if sys_parts:
            invoke_messages = [SystemMessage(content="\n\n".join(sys_parts))] + list(messages)
        else:
            invoke_messages = list(messages)
        response = await _bound_model.ainvoke(invoke_messages)
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
