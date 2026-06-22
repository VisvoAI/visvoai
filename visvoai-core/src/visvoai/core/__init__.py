"""
visvoai.core — Extensible Python agent runtime.

Provides the AgentRuntime base class, BaseAgentTool + auto-registration,
RuntimeContext (surface-agnostic), ToolPersistence interface, and the core
LangGraph loop (agent→tools, dynamic MCP tool retrieval via Plan A).

Public API (populated as code is migrated from backend/):
  from visvoai.core import AgentRuntime, AgentState
  from visvoai.core.tools import BaseAgentTool, ToolPersistence, RuntimeContext
  from visvoai.core.registry import build_registry
"""
