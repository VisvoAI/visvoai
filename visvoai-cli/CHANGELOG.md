# Changelog — visvoai-cli

Versions follow `v0.MINOR.PATCH` while unstable (pre-1.0): MINOR for new capability or
breaking changes, PATCH for fixes. No major bump until the surface stabilizes.

## [0.3.1] — 2026-06

### Fixed
- `pip install visvoai-cli` now bundles **all** provider integrations
  (`visvoai-ai[all]` — Gemini incl. grounded search, Anthropic, OpenAI + any
  OpenAI-compatible provider), so every model in the picker's catalog runs out of
  the box. Previously the base install carried only the Gemini lib, so selecting a
  Claude/OpenAI model crashed with `No module named 'langchain_openai'` /
  `langchain_anthropic`. The model picker exposes the full models.dev catalog, so a
  single-provider install was a footgun; leanness stays in visvoai-ai's extras, not
  the app.

## [0.3.0] — 2026-06

### Added
- **Configurable context-assembly pipeline** (`context/`): per-turn system-prompt
  assembly via `CLIRuntime._build_agent_node`, replacing the single static prompt.
  Ordered providers (`base_prompt`, `project_instructions` — auto-discovers AGENTS.md /
  CLAUDE.md up from cwd —, `environment`, `datetime`, `git_state`), each budget-clipped.
  Static providers form a byte-stable cacheable prefix; per-turn providers the volatile
  suffix. Configurable via `.visvoai/context.toml` (`[context]`, layered project→global):
  toggle/order/budget per provider, plus a global token budget (truncate-per-section).
- **Path confinement** (`pathguard.py`): `write_file`/`edit_file` are confined to the
  working directory (+ `[permissions].write_roots`); symlink/`..` escapes and writes into
  `.git/` are rejected. Reads stay unconfined. Applied in both tool sets.
- **Permission policy** (`permissions.py`): pre-authorize known-safe ops in
  `.visvoai/config.toml [permissions]` (`allow_shell` command prefixes, `allow_write`
  globs) so the gate skips them.
- **Graduated HITL approval modes** (`hitl_modes.py`): normal / auto-edit / accept-all,
  cycled live by **shift+tab** or `/mode`, shown as a status-bar chip. Auto-edit
  auto-approves file writes but still gates shell. Session-only (resets to normal).
  Modes relax approval only — path confinement is never relaxed.
- Single-shot `--yes`/`-y`: headless runs now **deny mutations by default** (except
  policy-allowed ops); `--yes` opts into auto-approve. Path confinement applies regardless.

### Changed
- File-mutation tools (`tools/files.py`) are now built per-cwd via `make_write_file` /
  `make_edit_file` factories (path-confined); read-only tools stay module-level.
- Info-level toast notifications are suppressed (status bar / inline UI carry state);
  warning/error toasts still show.

## [0.2.0] — 2026-06

### Added
- **Dynamic model catalog** (`catalog.py`): at startup the CLI installs
  `build_catalog([BakedSource(), RemoteModelsDevSource(cache)])` so the model picker
  reflects the live models.dev catalog (~4000 models / ~128 providers), cached at
  `~/.visvoai/cache/models.json`, offline-tolerant via the bundled snapshot.
- `--refresh-models` flag — re-fetch the catalog (drops the cache) and exit.
- Picker filtering: shows the curated baked deployments always, plus a provider's full
  models.dev catalog only when that provider has a configured key — abundance without
  drowning the list.

### Changed
- **Model page redesigned** (`screens/model_view.py`): replaced the per-model Widget list
  (which mounted ~2000 widgets and lagged at catalog scale) with a virtualized `OptionList`
  + a live search `Input`. Provider grouping (connected first, locked tagged "· needs key"),
  aligned ctx/thinking/cost columns, spacing between groups. Rows render only when visible.
  Adds **sort** (⌃s: name / cost / context, within each group) and **filter** toggles
  (⌃t thinking-only, ⌃k connected-only).
- **Conversations list** (`screens/sessions.py`): grouped by recency — Today / Yesterday /
  Last 7 days / Last month / Older — with spacing and centered layout matching the model page.

### Requires
- `visvoai-ai >= 0.2.0` (catalog engine APIs).

## [0.1.0]
- Initial CLI: Textual TUI + single-shot, layered API-key storage, model/thinking picker.
