# tools

The agent's tool set — plain LangChain `@tool` functions (no datastore, pure local
ops), grouped by concern. Every tool caps its output so one call can't flood the
model's context, and returns `ERROR: …` as data (never raises) so the agent recovers.

# Key Files
- `__init__.py` → aggregator: applies `inspect.cleandoc` to each docstring, exposes `build_cli_tools()` + re-exports every tool/cap.
- `files.py` → `read_file` (paginated), `write_file`, `edit_file`, `list_files`, `list_tree` (bounded tree) + tree helpers + their caps.
- `shell.py` → `run_shell` (30s, combined stdout/stderr + `[exit:N]` marker) + `SHELL_LINE_CAP`.
- `web.py` → `web_search` (grounded answer + sources) / `web_fetch` (one URL → markdown), both delegating to the `visvoai-ai` seam; `WEB_LINE_CAP`.
- `_common.py` → shared output bounds: `cap_lines`, `clip_line`, `MAX_LINE_LEN`.

# Conventions
- A tool returns its result/error as a string; it never raises out of `_execute`.
- Web tools NEVER import a provider SDK — they call `visvoai.ai.run_search` / `fetch_url`, keeping the SDK in one package.
- New caps live next to the tools that use them; genuinely shared ones go in `_common.py`.

# Gotchas
- `run_shell` caps the body BEFORE appending `[exit:N]` so the marker survives truncation (the UI parses it for success/failure).
- `list_tree` is bounded on depth, per-dir fan-out, AND total — each truncation is marked so the agent can drill into a subpath.
