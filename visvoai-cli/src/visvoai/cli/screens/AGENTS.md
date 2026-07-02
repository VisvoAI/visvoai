# screens

Full-screen Textual views pushed over the main conversation (model picker, session
resume, git commit). Each `dismiss(...)`es a result the caller awaits.

# Key Files
- `base.py` → `BlendScreen` — shared base that paints the detected terminal background so a screen blends with the app.
- `model_view.py` → `ModelScreen` (the model page): a virtualized `OptionList` + search `Input` (handles the full ~4000-model catalog), grouped by provider (connected first, locked tagged "· needs key"), aligned ctx/thinking/cost columns + `ThinkChip` (thinking-level chooser). Sort (⌃s name/cost/context, within group) + filters (⌃t thinking-only, ⌃k connected-only). Returns `(deployment_id, level)`. Search input style matches `SessionsScreen`.
- `sessions.py` → `SessionsScreen` — resume a past conversation. Rows grouped by recency via `_date_group(ts)` (Today / Yesterday / Last 7 days / Last month / Older) off each session's `_sort` epoch; centered layout matching the model page.
- `git_view.py` → `GitScreen` (interactive staging + commit over real git via `gitio`): `GitFileRow` + `CommitMessageArea`; adaptive list→diff two-column layout.
- `rewind_view.py` → `RewindScreen` — pick a checkpoint to rewind/branch to (active-branch chain newest-first, per-row file-diff counts). `dismiss(checkpoint_id | None)`. Used by `/rewind`, and by `/branch`+`/fork` to choose a point.
- `branch_view.py` → `BranchScreen` — switch conversation branches or start a new fork; a leading `NEW_BRANCH` ("+new") sentinel row. `dismiss(branch_name | '+new' | None)`.
- `mcp_view.py` → `MCPScreen` — MCP server status (untrusted-first ordering), setup help when empty, and trust-toggling for project-defined servers (enter marks pending; applied by the caller on close). `dismiss(list[str])` — server names to trust. Infrastructure state deliberately lives here, not in the chat log.

# Conventions
- Screens subclass `BlendScreen` (not raw `Screen`) so the background matches the app.
- Driven by plain data passed in (e.g. a `DeployView` list, a git status) — they don't import `visvoai.ai`/`gitio` for data directly where the caller can supply it.

# Gotchas
- `GitScreen` accepts `cwd=None` to keep a mock mode for tests / the demo; real commits require a real cwd.
