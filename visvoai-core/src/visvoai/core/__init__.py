"""
visvoai.core — Extensible Python agent runtime.

Provides the AgentRuntime base class, RuntimeContext (surface-agnostic),
ToolPersistence / LLMPersistence interfaces, the public AgentState TypedDict,
and BaseAgentTool for building tools.
"""
from visvoai.core.context import RuntimeContext
from visvoai.core.persistence import LLMPersistence, ToolPersistence
from visvoai.core.runtime import AgentRuntime
from visvoai.core.state import AgentState
from visvoai.core.tools import BaseAgentTool, tool_config
from visvoai.core.retrieval import ToolCatalog, build_catalog_from_servers

__all__ = [
    "AgentRuntime",
    "AgentState",
    "BaseAgentTool",
    "LLMPersistence",
    "RuntimeContext",
    "ToolCatalog",
    "ToolPersistence",
    "build_catalog_from_servers",
    "tool_config",
]
