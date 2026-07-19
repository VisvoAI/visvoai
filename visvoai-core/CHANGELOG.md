# Changelog — visvoai-core

Versions follow `v0.MINOR.PATCH` while unstable (pre-1.0): MINOR for new
capability or breaking changes, PATCH for fixes.

## [0.3.0] — 2026-07

### Added
- **Tool intake normalization** (`visvoai.core.adapt`): `build_graph` now
  accepts plain typed Python functions (sync or async — schema from type
  hints, description from the docstring), `BaseAgentTool` classes/instances
  (executed through the persistence lifecycle), and LangChain `BaseTool`s,
  mixed freely in one list. `as_tool` / `as_tools` / `as_tools_map` exported.
- `AgentRuntime.build_graph` matches the core builder: `all_tools_map`
  optional, `core_tools` accepts every tool shape (was still typed/required
  as LangChain-only at the runtime seam).
- Plain-function tools: a Google-style `Args:` docstring section becomes
  per-argument descriptions in the model-facing schema.
- `all_tools_map` is now optional — derived from `core_tools` when omitted.

## [0.2.0] — 2026-07

### Added
- **`AgentRuntime._get_state_class()`** — extend `AgentState` (TypedDict
  inheritance) with your own fields and have them flow through the graph,
  without overriding `build_graph`. Closes the gap between the documented
  seam ("extend AgentState") and reality (the state schema was hardcoded).
- **A real test suite** (30 tests): the loop's behavioral contract (routing,
  parallel tool calls, system-prompt injection), the soft step cap (clean
  finalize + the pathological case), per-round retrieval binding, every
  runtime hook from a consumer's seat (extend/replace nodes, routing,
  checkpointer, interrupts, state extension), the `BaseAgentTool` lifecycle,
  and `ToolCatalog` ranking/hybrid quality.

### Fixed
- **A pathological model can no longer loop past the step cap.** The cap's
  finalize round runs unbound (no tool declarations), so a well-formed model
  must answer — but a malformed provider that hallucinates tool calls anyway
  was routed back into the loop until the recursion limit. `should_continue`
  now forces END past the cap.

## [0.1.0] — 2026-06

Initial extraction from the platform: `AgentRuntime` + hooks, the core
agent→tools graph with soft step cap, `BaseAgentTool` lifecycle +
`tool_config` registration, `ToolPersistence`/`LLMPersistence` seams,
`RuntimeContext`, semantic tool retrieval (`ToolCatalog`).
