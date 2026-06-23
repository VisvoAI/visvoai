"""
visvoai.core.state — Public AgentState TypedDict.

A consumer adds its own fields on top of this via TypedDict inheritance:

  class MyState(AgentState, total=False):
      approval_request: ...
      pending_background_tasks: ...

This keeps the public AgentState free of surface-specific concerns while letting
a consumer extend it without forking the state machine.
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
      active_mcp_tools  — namespaced MCP tool names bound this round (dynamic
                          tool loading)

    Any state a consumer needs but core does not act on (plan-mode bookkeeping,
    approval flags, etc.) is intentionally NOT declared here — a subclass adds it.
    Core must not declare state it does not act on.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Dynamic MCP tool loading
    active_mcp_tools: Annotated[List[str], _union_ordered]
