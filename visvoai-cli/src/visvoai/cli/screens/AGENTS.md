# screens

Full-screen Textual views pushed over the main conversation (model picker, session
resume, git commit). Each `dismiss(...)`es a result the caller awaits.

# Key Files
- `base.py` → `BlendScreen` — shared base that paints the detected terminal background so a screen blends with the app.
- `model_view.py` → `ModelScreen` (the model page): `ModelRow` (name · context window · think · cost; connected-first grouping) + `ThinkChip` (thinking-level chooser). Returns `(deployment_id, level)`.
- `sessions.py` → `SessionsScreen` — resume a past conversation from the real store.
- `git_view.py` → `GitScreen` (interactive staging + commit over real git via `gitio`): `GitFileRow` + `CommitMessageArea`; adaptive list→diff two-column layout.

# Conventions
- Screens subclass `BlendScreen` (not raw `Screen`) so the background matches the app.
- Driven by plain data passed in (e.g. a `DeployView` list, a git status) — they don't import `visvoai.ai`/`gitio` for data directly where the caller can supply it.

# Gotchas
- `GitScreen` accepts `cwd=None` to keep a mock mode for tests / the demo; real commits require a real cwd.
