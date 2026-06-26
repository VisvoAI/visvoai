# visvoai-cli

A terminal-native coding agent built on `visvoai-core` + `visvoai-ai`: a Textual
TUI (interactive REPL) plus a single-shot mode. The agent reads/edits files, runs
shell commands, searches the web, and renders its work — streaming replies, tool
activity, diffs, thinking, and mermaid diagrams — in the terminal.

Two surfaces, one console script (`visvoai`):
- `visvoai`            → launch the Textual TUI
- `visvoai "prompt"`   → single-shot: stream one turn to stdout

# Key Files
- `main.py` → the `visvoai` entry point: no prompt → `_launch_tui` (VisvoApp); a prompt → `_run_single_shot` (CLIRuntime graph → `astream_events` → stdout). Both build the model via `visvoai.ai.build_chat_model`.
- `app.py` → `VisvoApp` — the Textual app: shell (CSS, bindings, compose/lifecycle, theme, welcome, quit/clear) + shared turn/HITL primitives (`_begin_turn`/`_mount_block`/`_tool_node`, `ask_choice`/`ask_form`/`ask_text`). Composed from mixins.
- `agent_turn.py` / `commands.py` / `sessions.py` / `render.py` / `demo.py` → VisvoApp mixins (real turn, slash commands, resume/screens, answer+mermaid rendering, the test-only mock).
- `agent.py` → pipeline glue: `build_agent_graph` (provider → CLIRuntime graph), chunk classification, `SYSTEM_PROMPT`, deployment/usage/cost views. Textual-free.
- `runtime.py` → `CLIRuntime(AgentRuntime)` — the default agent→tools loop, no interrupts/checkpointer.
- `context.py` → `CLIContext(RuntimeContext)` — cwd / terminal width; no auth/datastore.
- `store.py` → folder-per-conversation persistence (`history.jsonl` + `meta.json` + `receipts.jsonl`), no DB.
- `keys.py` → layered API-key resolution + storage: `load_keys_into_env(cwd)` (env > project secrets > global config), `set_key(provider, key, scope, cwd)` (0600, auto-gitignore for project).
- `catalog.py` → `install_cli_catalog()` — at startup installs `build_catalog([BakedSource(), RemoteModelsDevSource(cache)])` as the default registry so the picker shows the live models.dev catalog (cached `~/.visvoai/cache/models.json`, offline-tolerant). `--refresh-models` re-fetches. The picker (`agent.chat_deployments`) shows curated baked deployments always + a provider's full catalog only when keyed.
- `gated_tools.py` → edit/write/shell behind a permission gate; web tools ungated.
- `gitio.py` → real git: working-tree status / stage / unstage / commit / project files.
- `mermaid.py` → ```mermaid fence → segments + a self-contained HTML viewer (pure helpers).
- `theme.py` / `grid.py` / `termbg.py` → 12-palette theme (reads `palette_tokens.json`), grid alignment, terminal-bg detection.
- `tools/` → the agent tool set (files/shell/web split; see `tools/`).
- `widgets/`, `screens/` → reusable Textual widgets and full-screen views (each has its own AGENTS.md).
- `palette_tokens.json`, `assets/` → shipped package data (see `[tool.setuptools.package-data]`).

# Key Classes / Functions
- `VisvoApp(App)` → the Textual app; exposed lazily via `visvoai.cli.__getattr__` so `import visvoai.cli` / single-shot don't pull in Textual.
- `CLIRuntime(AgentRuntime)` → no `_extend_graph` additions — the pure core loop.
- `cli` (main.py) → Click command, the `visvoai` console script; routes prompt→single-shot, no-prompt→TUI.
- `build_agent_graph()` (agent.py) → builds the graph the TUI streams; `build_chat_model` applies the deployment's default thinking.

# Conventions
- Pure public-package consumer: imports only `visvoai-ai`, `visvoai-core`, relative modules, and declared third-party deps (textual, rich, click, pygments, python-dotenv, langchain-google-genai). NEVER a private/platform module.
- No private names in shipped text (docstrings/comments/AGENTS.md) — boundary rule 2.
- Every widget owns its styling via Textual `DEFAULT_CSS`; colours come only from `theme.py`.
- `app.py` holds the shell + shared primitives; feature concerns live in mixins.
- No graph interrupts/checkpointer — the CLI is synchronous (the human is in the loop).

# Gotchas
- API keys: `main._bootstrap_env(cwd)` (both surfaces) loads `.env` then fills `os.environ` from the stored layers. Precedence is env > project (`.visvoai/secrets.toml`, gitignored) > global (`~/.visvoai/config.toml` `[api_keys]`); an exported var always wins. Keys NEVER go in the committed `.visvoai/config.toml`. Per-provider: the active model's provider determines which `{PROVIDER}_API_KEY` is needed; web search/fetch always need Gemini's. Add a key via `/login` (TUI) or `visvoai --set-key <provider>`.
- `astream_events` is called with an explicit `recursion_limit=100` (both surfaces) — the LangGraph default 25 crashes a deep turn before the core graph's soft step cap can force a clean finalize.
- The mock showcase (DemoMixin + mock.py) is kept for tests but is NOT reachable from the menu, by typing `/demo`, or any key binding — tests drive it via `run_command`.
- `theme.py` reads `palette_tokens.json` from its own directory at import time → it must ship as package data (it does).
- Tests live in `tests/` and run in the package's own env (`uv run --extra dev pytest`); `[tool.uv.sources]` resolves the sibling packages by path for dev (pip/PyPI ignore that table).
