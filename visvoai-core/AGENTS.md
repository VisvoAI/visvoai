# visvoai-core

Extensible Python agent runtime. Provides the public extension surface for
building surfaces (CLI, server, IDE) on top of the agent loop.

# Key Files
- `BUILD-YOUR-OWN.md` → the adaptation guide: four decisions + hook table — the answer to "how do I fork/build on this"
- `src/visvoai/core/__init__.py` → public API surface
- `src/visvoai/core/adapt.py` → boundary layer: tool intake normalization + `ask()` text-in/text-out invoke (`as_tool`/`as_tools`/`as_tools_map`): plain functions / BaseAgentTool / LangChain BaseTool → the loop's currency, once, at the boundary; build_graph accepts all three mixed
- `src/visvoai/core/graph.py` → lean core `build_graph()` (no extra nodes/deps)
- `src/visvoai/core/runtime.py` → `AgentRuntime` base class with 4 hook methods
- `src/visvoai/core/state.py` → public `AgentState` TypedDict (core fields only)
- `src/visvoai/core/tools.py` → `BaseAgentTool` ABC + `ToolConfig` + `@tool_config` decorator + auto-registration
- `src/visvoai/core/results.py` → minimal `ToolResult` envelope (tool_name/status/result/data + 4 factories) + `ToolStatus` (4 outcomes)
- `src/visvoai/core/persistence.py` → `ToolPersistence` + `LLMPersistence` no-op interfaces
- `src/visvoai/core/context.py` → `RuntimeContext` (3 surface-agnostic fields: request_id, subagent_depth, parent_tool_call_id)
- `src/visvoai/core/retrieval.py` → `ToolCatalog` (BM25 + optional cosine-hybrid); `build_catalog_from_servers()`; `make_per_round_retrieve()`

# Key Classes / Functions
- `AgentRuntime` → buildable base class; override `_extend_graph()`, `_build_agent_node()`,
  `_build_tools_node()`, `_agent_routing()`, `_tools_routing()`, `_get_checkpointer()`, `_get_interrupt_nodes()`
  to add custom behavior. The three node/routing hooks each receive a `GraphBuildContext` and return
  `None` (use core default) or a value (override): `_build_agent_node` → the agent node, `_build_tools_node`
  → the tools node (default `ToolNode`), `_agent_routing` → `(fn, map)` for the agent→X edge
  (default `should_continue` → `{tools, END}`). Together they let a rich consumer express its whole builder
  through hooks instead of overriding `build_graph`.
- `GraphBuildContext` → frozen dataclass of build inputs (model, core_tools, all_tools_map, all_tools,
  system_prompt, tool_configs, per_round_retrieve, lean_prompt, max_agent_steps) handed to the node/routing
  override hooks. Generic inputs only — surface-specific state lives on the runtime subclass.
- `AgentState` → LangGraph TypedDict: `messages`, `active_mcp_tools` only. State a consumer
  needs but core does not act on (plan-mode bookkeeping, approval flags, …) is deliberately
  NOT here — a subclass adds it via TypedDict inheritance.
- `BaseAgentTool` → ABC with `_persistence` injection, `execute()` lifecycle, auto-registration
  via `__init_subclass__`. Registered tools accumulate in `BaseAgentTool._registry`.
  A consumer that needs more axes (UI metadata, approval, access roles, background) subclasses
  this together with its own `ToolConfig` subclass, and may keep its own `_registry`.
- `ToolConfig` → plain class declaring the generic config fields — the SINGLE source. `BaseAgentTool` inherits it so `tool.is_core` etc. are readable class attrs. NOT a pydantic model (fields must inherit as plain attrs).
- `build_config_validator(config_cls)` → derives a pydantic validator from a config class's annotations, so `@tool_config` coerces/validates without a second hand-maintained schema. A consumer's `ToolConfig` subclass can reuse it.
- `tool_config(**kwargs)` → decorator; coerces/validates kwargs via the `ToolConfig`-derived validator at import time (e.g. `is_core="yes"` → `True`), sets only passed fields (rest inherit `ToolConfig` defaults).
- `ToolResult` → minimal result envelope (model-facing `result` + generic `data` bag, canonical payload at `data["output"]`). Factories: `.success/.invalid_input/.tool_error/.empty`. A consumer can subclass it to widen `status` and add fields.
- `ToolStatus` → 4 basic outcomes (SUCCESS/EMPTY_RESULT/INVALID_INPUT/TOOL_ERROR). A consumer that needs extra outcomes (e.g. approval states) adds them on its own subclass.
- `ToolPersistence` → no-op lifecycle hooks (on_start, on_resume, on_complete, on_error).
- `LLMPersistence` → no-op hooks (on_call_complete, on_thinking_log).
- `RuntimeContext` → surface-agnostic state (request_id, subagent_depth, parent_tool_call_id). Anything surface-specific (auth, datastore session, plan/skill bookkeeping) belongs on a subclass.
- `ToolCatalog` → BM25 index; `search(query, k, query_vec=None)` returns tool names;
  HYBRID mode (BM25 ∪ cosine union) when query_vec + per-tool embeddings are present.
- `build_catalog_from_servers(servers)` → constructs ToolCatalog from server objects.
- `make_per_round_retrieve(catalog, k, embed_query=None)` → builds the `per_round_retrieve(query)->[name]` closure for `build_graph`. `embed_query` is the seam for semantic ranking; `None` ⇒ BM25-only (zero embedding infra).

# Conventions
- No datastore, no HTTP, no auth, no private/consumer imports in any file in this package.
- `ToolPersistence` / `LLMPersistence` defaults are no-ops; a consumer injects a concrete subclass to record events.
- `AgentRuntime.build_graph()` calls `visvoai.core.graph.build_graph()` (the lean version); a consumer may override it to call its own richer builder.
- Public docstrings describe the generic extension seam only — never a specific private consumer by name.

# Gotchas
- `AgentRuntime._extend_graph()` is called BEFORE the tools→X routing edge is added —
  a subclass must add its own nodes there; then `_tools_routing()` handles the edge.
- `BaseAgentTool._registry` is a class-level list shared across all tool classes.
- `ToolCatalog` BM25 uses lowercase tokenization across both names and descriptions.
- `build_graph`'s per-round retrieval is **transient** — the retrieved set is used for THIS round's tool binding only, never written back to `active_mcp_tools` (self-evicting). Tools NOT in `core_tools` are "deferrable" (bound on demand); with no retriever or no deferrables, binding is identical to bind-everything.
- `build_graph` forces a tool-free finalize at `max_agent_steps` agent rounds/turn (default `DEFAULT_MAX_AGENT_STEPS`, None disables) by invoking the UNBOUND model. This is the loop-safety invariant; it costs ~2 super-steps/round, so keep the caller's `recursion_limit` (set at invoke/astream time) above `2 * max_agent_steps`. Dedup / tool-failure-cap are deliberately NOT here yet — they are tools-node-level policies to add as opt-in knobs once the node-factory hooks exist.
- `BaseAgentTool.execute()` is an **override seam, not a hook seam**: it ships a default
  sync lifecycle (`on_start → _execute() → on_complete/on_error`). Normal consumers
  *inherit* it (implement `_execute()` only) and the loop *calls* it. A streaming consumer
  may *override the body* wholesale — a deliberate full-override, not a defect. Do NOT
  refactor this into a `super()` template-method; that would pull streaming concerns into
  core. Lifecycle behavior is pinned by `tests/test_tool_lifecycle.py`.
