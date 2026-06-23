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
- `AgentState` → LangGraph TypedDict: `messages`, `active_mcp_tools` only. Plan-mode
  fields (`active_plan`, `_plan_finalize_attempts`) are deliberately NOT here — plan-mode
  is a future opt-in plugin; the platform owns those fields in its extended state.
  Platform extends with plan-mode + HITL + bg_task fields.
- `BaseAgentTool` → ABC with `_persistence` injection, `execute()` lifecycle, auto-registration
  via `__init_subclass__`. Registered tools accumulate in `BaseAgentTool._registry`.
  Platform's `backend/tools/base.py:BaseAgentTool` SUBCLASSES this — inherits identity fields,
  the 13 generic config defaults, `_owned_resource_checks`, and `_persistence`; adds UI/HITL/roles/
  background axes and keeps its OWN `_registry` (distinct object, stricter discovery semantics).
- `ToolConfig` → plain class declaring the 13 generic config fields — the SINGLE source. `BaseAgentTool` inherits it so `tool.is_core` etc. are readable class attrs. NOT a pydantic model (fields must inherit as plain attrs).
- `build_config_validator(config_cls)` → derives a pydantic validator from a config class's annotations, so `@tool_config` coerces/validates without a second hand-maintained schema. Platform reuses it for `ToolMeta`.
- `tool_config(**kwargs)` → decorator; coerces/validates kwargs via the `ToolConfig`-derived validator at import time (e.g. `is_core="yes"` → `True`), sets only passed fields (rest inherit `ToolConfig` defaults)
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
- `BaseAgentTool.execute()` is an **override seam, not a hook seam**: it ships a default
  sync lifecycle (`on_start → _execute() → on_complete/on_error`). Normal consumers
  *inherit* it (implement `_execute()` only) and the loop *calls* it. The platform
  *overrides the body* to stream chunks — a deliberate full-override, not a defect. Do NOT
  refactor this into a `super()` template-method; that would pull streaming/HITL concerns
  into core. The default body currently has no live consumer (platform overrides it, CLI
  is a placeholder) — a lifecycle unit test is the open item.
