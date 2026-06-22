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
from typing import Annotated, Dict, Any, List, Optional, Sequence, TypedDict
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
    Public agent state. Platform surfaces extend this with their own fields.

    Fields:
      messages          — the conversation thread (add_messages reducer)
      active_plan       — structured plan steps (list of dicts)
      _plan_finalize_attempts — loop guard for finalize_check nudge
      active_mcp_tools  — namespaced MCP tool names bound this round (Plan A)
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Planning state
    active_plan: Optional[List[Dict[str, Any]]]
    _plan_finalize_attempts: Optional[int]

    # Dynamic MCP tool loading (Plan A)
    active_mcp_tools: Annotated[List[str], _union_ordered]
