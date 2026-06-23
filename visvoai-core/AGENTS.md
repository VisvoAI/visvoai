# visvoai-core

Extensible Python agent runtime. Provides the public extension surface for
building surfaces (CLI, web, IDE) on top of the agent loop.

# Key Files
- `src/visvoai/core/__init__.py` → public API surface
- `src/visvoai/core/graph.py` → lean core `build_graph()` (no HITL/platform deps)
- `src/visvoai/core/runtime.py` → `AgentRuntime` base class with 4 hook methods
- `src/visvoai/core/state.py` → public `AgentState` TypedDict (core fields only)
- `src/visvoai/core/tools.py` → `BaseAgentTool` ABC + `@tool_config` decorator + auto-registration
- `src/visvoai/core/results.py` → minimal `ToolResult` envelope (tool_name/status/result/data + 4 factories) + `ToolStatus` (4 outcomes)
- `src/visvoai/core/persistence.py` → `ToolPersistence` + `LLMPersistence` no-op interfaces
- `src/visvoai/core/context.py` → `RuntimeContext` (7 surface-agnostic fields)
- `src/visvoai/core/retrieval.py` → `ToolCatalog` (BM25 + optional cosine-hybrid); `build_catalog_from_servers()`

# Key Classes / Functions
- `AgentRuntime` → buildable base class; override `_extend_graph()`, `_tools_routing()`,
  `_get_checkpointer()`, `_get_interrupt_nodes()` to add platform behavior
- `AgentState` → LangGraph TypedDict: `messages`, `active_plan`, `_plan_finalize_attempts`,
  `active_mcp_tools`. Platform extends with HITL + bg_task fields.
- `BaseAgentTool` → ABC with `_persistence` injection, `execute()` lifecycle, auto-registration
  via `__init_subclass__`. Registered tools accumulate in `BaseAgentTool._registry`.
- `tool_config(**kwargs)` → decorator; validates metadata at import time and sets class attrs
- `ToolResult` → minimal result envelope (pi-style: model-facing `result` + generic `data` bag, canonical payload at `data["output"]`). Factories: `.success/.invalid_input/.tool_error/.empty`. Platform's `backend/models/query.py:ToolResult` SUBCLASSES this, widening `status` and adding question/sources/artifacts.
- `ToolStatus` → 4 basic outcomes (SUCCESS/EMPTY_RESULT/INVALID_INPUT/TOOL_ERROR). HITL statuses live in the platform enum, not here.
- `ToolPersistence` → no-op lifecycle hooks (on_start, on_resume, on_complete, on_error)
- `LLMPersistence` → no-op hooks (on_call_complete, on_thinking_log)
- `RuntimeContext` → surface-agnostic orchestrator state (7 fields)
- `ToolCatalog` → BM25 index; `search(query, k, query_vec=None)` returns tool names;
  HYBRID mode (BM25 ∪ cosine union) when query_vec + per-tool embeddings are present
- `build_catalog_from_servers(servers)` → constructs ToolCatalog from server objects

# Conventions
- No DB, no HTTP, no platform imports in any file in this package
- `ToolPersistence` default is no-op; platform injects `HistoryManagerPersistence`
- `LLMPersistence` default is no-op; platform injects `HistoryManagerLLMPersistence`
- `AgentRuntime.build_graph()` calls `visvoai.core.graph.build_graph()` (the lean version)
- Platform's `VisvoRuntime` overrides `build_graph()` to call `backend/agent/graph.py` instead

# Gotchas
- `AgentRuntime._extend_graph()` is called BEFORE the tools→X routing edge is added —
  subclass must add its own nodes there; then `_tools_routing()` handles the edge
- `BaseAgentTool._registry` is a class-level list shared across all tool classes
- `ToolCatalog` BM25 uses lowercase tokenization across both names and descriptions
