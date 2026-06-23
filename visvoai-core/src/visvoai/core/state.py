"""
visvoai.core.state — Public AgentState TypedDict.

Platform extensions add their own fields on top of this via TypedDict inheritance:

  class PlatformState(AgentState, total=False):
      hitl_request: ...   # HITL fields
      pending_background_tasks: ...

This keeps the public AgentState free of platform-specific concerns while allowing
the private platform to extend it without forking the state machine.
"""
import operator
from typing import Annotated, List, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def _replace(old, new):
    """Always-replace reducer — forces LangGraph to write the value even when it is None."""
    return new


def _union_ordered(old, new):
    """Order-preserving de-duplicating union reducer."""
    out = list(old or [])
    for x in (new or []):
        if x not in out:
            out.append(x)
    return out


class AgentState(TypedDict, total=False):
    """
    Public agent state — the lean agent↔tools loop. Surfaces and plugins extend
    this with their own fields via TypedDict inheritance.

    Fields:
      messages          — the conversation thread (add_messages reducer)
      active_mcp_tools  — namespaced MCP tool names bound this round (Plan A)

    Plan-mode state (active_plan, _plan_finalize_attempts) is intentionally NOT
    here: plan-mode is a future opt-in plugin, and the platform currently owns
    those fields in its own extended state. Core must not declare state it does
    not act on.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Dynamic MCP tool loading (Plan A)
    active_mcp_tools: Annotated[List[str], _union_ordered]
