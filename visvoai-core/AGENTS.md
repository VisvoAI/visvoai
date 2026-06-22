# visvoai-core

Extensible Python agent runtime. Provides the public extension surface for
building surfaces (CLI, web, IDE) on top of the agent loop.

# Key Files (once populated from backend/)
- `src/visvoai/core/__init__.py` → public API surface
- `src/visvoai/core/graph.py` → AgentRuntime class + AgentState TypedDict
- `src/visvoai/core/tools/base.py` → BaseAgentTool, ToolPersistence, RuntimeContext
- `src/visvoai/core/tools/registry.py` → build_registry(), ToolConfig, auto-registration
- `src/visvoai/core/retrieval/` → Plan A dynamic MCP tool retrieval (hybrid semantic search)

# Key Classes / Functions
- `AgentRuntime` → buildable base class; override _extend_graph(), _tools_routing(),
  _get_checkpointer(), _get_interrupt_nodes() to add platform behavior
- `AgentState` → LangGraph TypedDict with messages, hitl_*, active_plan, active_mcp_tools
- `RuntimeContext` → surface-agnostic orchestrator state (7 fields: request_id,
  subagent_depth, plan_state_ref, plan_lock, parent_tool_call_id, active_skill_resources,
  active_skill_id)
- `ToolPersistence` → no-op lifecycle hooks (on_start, on_resume, on_complete, on_error)
- `BaseAgentTool` → ABC with auto-registration via __init_subclass__, execute() lifecycle
- `build_registry()` → returns list of ToolConfig built from all registered subclasses

# Conventions
- No DB dependencies in core — HistoryManager lives in the private platform
- RuntimeContext fields only — no BackendContext fields in any core code
- ToolPersistence default is no-op; platform injects HistoryManagerPersistence via _persistence
- Auto-registration: every concrete tool class registers itself on definition (no manual list)

# Gotchas
- AgentRuntime._extend_graph() is called BEFORE tools→X routing edge is added —
  subclass must add its own nodes there; then _tools_routing() handles the edge
- When _runtime=None in build_graph(): existing platform HITL behavior is preserved
  (backward compat shim for orchestrator.py during migration)
