# Changelog — visvoai-cli

Versions follow `v0.MINOR.PATCH` while unstable (pre-1.0): MINOR for new capability or
breaking changes, PATCH for fixes. No major bump until the surface stabilizes.

## [0.6.0] — 2026-07

### Added
- **Background processes.** The agent can now run dev servers and watchers properly:
  `start_process("yarn dev")` returns a process id immediately;
  `check_process(id, wait_seconds=…)` reads new output (waiting for a "ready" line
  instead of polling); `stop_process(id)` terminates the whole process group. Output
  is captured to a bounded ring buffer — a chatty server can't blow memory, and the
  child never blocks on a full pipe.
- **`/ps` screen** — see what's running (live runtimes, last output line), stop a
  process with enter, dismiss finished ones. A `⏵ N procs` footer chip appears
  whenever something is running so nothing is ever invisible.
- **No orphans.** Every process group the agent started is killed on app exit (TUI
  and one-shot runs alike) — a closed CLI never leaves a server squatting on a port.
- Starting/stopping a process is approval-gated like shell; reading output is free.
  A user-stopped process reports "stopped by the user" to the agent on next check.

### Fixed
- **MCP sessions are now persistent** — one live session per server for the app's
  lifetime, instead of a fresh subprocess per tool call. Stateful servers finally
  work: with chrome-devtools-mcp, a page opened in one call no longer vanishes by
  the next (each call was silently getting a brand-new browser). Sessions close on
  app exit and when /mcp trust or config changes force a re-connect.
- A cancelled turn (esc / quit mid-turn) no longer crashes with `NoMatches` when its
  cleanup races app teardown — footer updates degrade to no-ops once widgets unmount.
- `run_shell` crashed the whole turn with `TypeError` when a command timed out while
  a backgrounded child held the stdout pipe open (Python quirk:
  `TimeoutExpired.stdout` is bytes even with `text=True`). Timeouts now return
  partial output as data, and the docstring teaches the correct detach idiom.

## [0.5.0] — 2026-07

### Added
- **MCP servers.** Configure `[mcp_servers.<name>]` tables in `~/.visvoai/config.toml`
  (personal) or `<project>/.visvoai/config.toml` (shared via the repo; project wins on
  name collisions). Both stdio servers (`command` + `args` — the CLI spawns the
  subprocess) and remote streamable-HTTP servers (`url` + `headers`) are supported;
  `${VAR}` values expand from the environment, so secrets ride the existing layered
  key system and never live in config. Discovered tools are named `server__tool` and
  join the agent's toolset; in gated modes each call needs the same approval as shell.
- **`/mcp` command.** A full-screen server view (like `/model`) with live status
  (✓ connected · tool count, ✗ failed · why, ! untrusted, · disabled), setup help
  when nothing is configured, and first-use trust approval for project-defined
  servers — infrastructure state stays out of the conversation log.
- **Project-server trust.** A repo's config can define servers (including subprocesses),
  so project-defined servers never connect without a one-time local approval — recorded
  outside the repo, keyed to a hash of the server spec (editing the spec re-prompts;
  rotating a token doesn't).
- Dead or slow servers can't hang the TUI: per-server 10s connect timeout, failures
  reported in `/mcp` and skipped.
- **`visvoai mcp add/list/remove` subcommands** — script-friendly server management
  in the Claude-Code style: `visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest`,
  `visvoai mcp add linear --url … --header 'Authorization=Bearer ${VAR}'`. Writes the
  config TOML surgically (everything else in the file, comments included, is preserved),
  warns when a header/env value looks like a pasted raw secret, and `--project` targets
  the repo-shared config. The `visvoai` entry point is now a command group with `chat`
  as the default command — bare prompts and all existing flags work unchanged.
- `/mcp` empty state now teaches all three setup paths: the subcommand, hand-editing
  the config (with a copy-paste example), or just asking the agent to write it.

## [0.4.3] — 2026-07

### Changed
- **`/rewind` offers granular actions at a question** (like a familiar coding-agent
  menu), because we track the code and conversation axes separately: *Revert code +
  conversation*, *Revert conversation only* (keep current files), *Revert code only*
  (keep the chat), *Summarize up to here* (fold older turns via a chosen cut point), or
  *Branch from here*. The split-axis reverts record a fresh checkpoint so code + chat
  stay coherent afterward.
- **`/rewind` is now question-oriented.** The picker was a flat list of checkpoints
  tagged "turn end / before tools / start" — confusing, and it offered no way to rewind
  to a *question* (only to tool boundaries). It now lists YOUR QUESTIONS (newest first),
  each with a one-line summary of what that turn did underneath; selecting one restores
  files + chat to the moment just before you asked it (then rewind-in-place or branch).
  Every question is a target, including the most recent (so you can undo the last turn).
  The `/branch`-new and `/fork` pickers use the same clear turn view.

- More breathing room between turns — each question now has a clear 2-line break above
  it (the answer stays attached below), so the transcript reads less congested.

### Fixed
- **Branch-switch/fork no longer silently overwrites uncommitted hand-edits.** Switching
  branches (or forking from an earlier checkpoint) restores that branch's files — but if
  you'd hand-edited a file since the last turn (so no checkpoint captured it), the restore
  wiped it unrecoverably. Now the current branch's working-tree drift is snapshotted
  ("manual edits" checkpoint) before the restore, so it's preserved and recoverable via
  /rewind. No-op when the tree already matches the last checkpoint.

### Changed
- **`/compact` is now real.** It was a mock (a fake "18 messages folded", hardcoded
  14%). It now LLM-summarizes the older prefix into a dense continuation note, keeps the
  last 2 turns verbatim (never splitting a turn), rewrites the active-branch thread to
  `[summary] + tail`, realigns per-turn receipts, and sets the context gauge from the
  actual compacted size (the next turn replaces the estimate with real usage). File
  history is untouched (compaction is a conversation op); the rewind timeline resets to
  a single post-compaction floor, and older file commits stay reachable via their refs.
  No-op with a clear reason when there's too little to fold or the summary is empty.

## [0.4.2] — 2026-07

### Changed
- **Tool-result management.** The model API is stateless, so the whole thread (incl.
  every tool result) is re-sent on each call. When building the model input we now keep
  the most recent tool results verbatim up to a char budget and elide older large ones
  to a stub (id preserved, so the model can re-run the tool if needed) — bounding
  carried-over context across turns. Model-agnostic; transforms only the sent copy, the
  durable thread keeps full fidelity (rewind/replay/persistence unaffected). Note: this
  bounds cross-turn growth, not the intra-turn re-sends of a single heavy tool loop
  (that needs per-call handling in the runtime, or prompt caching).

## [0.4.1] — 2026-07

### Fixed
- **`/rewind` silently did nothing when visvoai was launched in the home directory.**
  `resolve_project_id` anchored on the global `~/.visvoai/config.toml`, so the shadow
  repo's work tree became `$HOME` and `git add -A` over the whole home dir failed/timed
  out — and the error was swallowed, leaving 0 checkpoints and an empty `/rewind`. Now:
  checkpointing refuses to run when the working directory is the home dir / filesystem
  root (anything containing the `~/.visvoai` data dir) and says so once; and any
  snapshot failure disables checkpointing loudly-once instead of silently — so `/rewind`
  being unavailable is always explained.

## [0.4.0] — 2026-06

### Added
- **Git-structured history.** A shadow git repo (separate GIT_DIR over the project
  root; the user's own `.git` is never touched) snapshots the whole work tree per tool
  batch and at turn end, each linked to a message index so code and conversation move
  together. Honours `.gitignore` + default excludes; content-addressed dedup makes
  no-change turns free.
  - `/rewind` (Ctrl+B) — restore files **and** conversation to an earlier checkpoint
    (TRUE restore: revert + un-delete + remove-new), or **branch from here** to keep both.
  - `/branch` — switch timelines or fork a new one; each branch has its own thread,
    receipts, and code tip.
  - `/fork` — materialize a checkpoint in a new directory (git worktree) + a seeded
    conversation, to run a second timeline in parallel.
  - `/export` — a markdown transcript, or a self-contained bundle (transcript + thread
    + a restorable git bundle of the code).
  - `/log` — the active branch's checkpoint chain.
  - On resume, a drifted work tree records a baseline of current reality; rewinding past
    it warns that out-of-session changes will be discarded.
  - All best-effort: missing git or any checkpoint error is swallowed — it never breaks
    a turn.
- **Onboarding & self-driving guidance** — teach features by context, never nag:
  - Launch-state welcome (first-time onboarding · returning-but-empty nudge · standard)
    and a "what's new" panel showing CHANGELOG entries since your last visit.
  - A sectioned `/help` (Chat / Time travel / Project + keyboard table + a plain-English
    explainer) and `/tour`, an opt-in 60-second walkthrough.
  - Rotating spinner tips that **adapt** — a feature's tip stops once you've used it and
    an undiscovered one surfaces; contextual post-turn nudges (files changed → /rewind or
    /commit; a tool failed → /rewind) that self-silence once learned; and one-time
    coachmarks (first checkpoint, first approval).
  - Typing an unknown `/command` suggests the closest (`/undo` → /rewind); the prompt
    placeholder rotates example tasks; a returning project with uncommitted changes gets
    one quiet "N changes — /commit to review" line at launch.

## [0.3.4] — 2026-06

### Fixed
- A failed tool's error message rendered vertically (one character per line). The
  failure body `list()`-ed a str into characters; it now splits on newlines.

## [0.3.3] — 2026-06

### Added
- `run_shell` takes an agent-settable `timeout_seconds` (default 30, clamped to 600)
  — the agent can request longer for installs/builds/full test suites instead of
  dying at a fixed 30s.

### Changed
- **Crash-durable persistence.** The human message and each completed AI/Tool message
  are flushed to the conversation store AS they stream (idempotent tail-append), so a
  hard crash mid-turn no longer loses the turn. The durable log is append-only; a
  dangling tool_call from a crashed/errored turn is stripped at point-of-use by
  `_sanitize_thread` when building model state (also covers resumed threads).
- Concurrent tool approvals are serialized (`_hitl_lock`) — `ToolNode` runs tool_calls
  in parallel, so multiple HITL prompts no longer mount/contend at once; a sibling's
  "allow all this session" skips the redundant prompt.
- A "preparing tool call…" status shows while the model streams tool-call arguments
  (no more silent spinner gap before a tool starts).

### Fixed
- Picks up `visvoai-ai` 0.2.2 — catalog ids that can't be encoded (cloudflare `@cf/…`)
  no longer appear in the model picker as crashing entries.

## [0.3.2] — 2026-06

### Fixed
- **Shell timeouts are tool errors, not turn crashes.** `run_shell` (and the gated
  variant) now catch `subprocess.TimeoutExpired`/spawn errors and return them as
  `ERROR: …\n[exit: -1]` data — the agent recovers and the turn survives, instead of
  the timeout propagating up and killing the turn.
- **Turn failures render as a proper `ErrorBlock`**, not a system note —
  classified auth / network / model with a human message (`_classify_turn_error`).
- **Errored/interrupted turns no longer lose their work.** When the root
  `on_chain_end` never fires, the thread is rebuilt from the human turn + the
  messages that completed (`_valid_thread_suffix` trims any dangling tool_call so the
  saved thread stays replayable). Previously only the human message persisted.
- Picks up the `visvoai-ai` key-cleaning fix (trailing space/quotes → silent 401).

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
