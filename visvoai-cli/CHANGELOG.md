# Changelog — visvoai-cli

Versions follow `v0.MINOR.PATCH` while unstable (pre-1.0): MINOR for new capability or
breaking changes, PATCH for fixes. No major bump until the surface stabilizes.

## [0.14.1] — 2026-07

### Changed
- **Internal: one spec store instead of three.** The layered-loading + trust
  machinery that mcp.py, agents.py and skills.py each hand-copied (merge
  precedence, the coincident-layer guard, `<kind>_trust.toml` read/write/
  check) now lives once in `specstore.py` (`LayeredSpecStore`). No behavior
  change — existing trust files keep working; the coincident-layer bug class
  is now structurally impossible rather than patched per module. Layers are
  pluggable providers, sized so a future artifacts store (or a DB-backed
  layer) is a consumer, not a copy.

## [0.14.0] — 2026-07

### Added
- **Skills — reusable workflows the AI loads on demand.** A skill is a
  directory: `~/.visvoai/skills/<name>/SKILL.md` (personal) or
  `.visvoai/skills/<name>/SKILL.md` (project, shareable; project wins on
  name; a flat `<name>.md` also works). Frontmatter: `description:` (the
  index line) + optional `args:` block of named `$placeholders`; the body is
  the instructions. The AI sees a compact index in its `read_skill` tool and
  loads a skill's full instructions only when a request matches — supporting
  reference files next to SKILL.md are read lazily via `resource=`, never
  speculatively (progressive disclosure, same model as the platform).
  A skill grants KNOWLEDGE, not capability: the AI follows the instructions
  with its own tools, and mutations still ask you. Skills are available to
  subagents too (every tier — read-only included).
- **/skills screen** — the roster with args/resources per skill, plus
  one-time trust approval for project-defined skills (a repo-controlled body
  still steers this machine's tools; any edit re-prompts). Pending-approval
  toasts cover skills exactly like agents.
- **`visvoai skills list/show/create/remove`** — manage skills headlessly;
  `create` is an interactive wizard. Or ask the agent to write one.
- **External skill libraries (`extra_dirs`).** Point the CLI at skill folders
  you already have — another CLI's `~/.claude/skills`, a repo's `skills/`
  tree, shared dotfiles — via `[skills] extra_dirs = [...]` in
  `~/.visvoai/config.toml` (personal) or the project's
  `.visvoai/config.toml` (shareable). Trust follows the DECLARING config:
  user-config dirs load as global (implicitly trusted), project-config dirs
  load as project (one-time approval). Precedence: global dir → global
  extras → project dir → project extras; later wins on name. Foreign
  frontmatter (Claude Code's name/description keys) parses as-is.

### Fixed
- **Global definitions no longer reload as "project" outside a project.**
  project_root() walks up looking for `.visvoai/config.toml` — and the GLOBAL
  `~/.visvoai/config.toml` matches, so from any directory without its own
  project anchor the "project" layer resolved to the global dir itself,
  reclassifying global skills/agents/MCP servers as project-defined and
  demanding trust approval for things the user wrote. The project layer is
  now skipped when it coincides with the global one (all three loaders).
- **A stalled agent run no longer masquerades as success.** run_agent
  returned the last NON-EMPTY message as the "final answer" — so a provider
  stall after mid-run narration (live incident: a garbled MiniMax tool call
  ended the loop on an empty message) surfaced stale narration as the
  result, marked done. Only the terminal message counts now; a stall returns
  an explicit ERROR with the completed-step count and a pointer to /runs.

## [0.13.0] — 2026-07

### Changed
- **An agent run is now a first-class agent conversation.** Rebuilt around one
  principle: a run is the same thing as a main turn, minus the human — so it
  gets the same treatment everywhere.
  - **Same rendering**: run activity is structured steps rendered with the
    conversation's own ToolRow widgets (verb + consequence color, spinner,
    ✓/✗ + duration on the rail) in both the side panel and /runs — no more
    timestamped log lines. A step's row transitions in place when it
    completes, exactly like a chat tool row.
  - **Same durability**: the trace file is appended live — meta at dispatch,
    each step as it completes, summary at the end. A hung or killed run
    leaves its partial transcript on disk, like a crashed main turn keeps its
    persisted messages.
  - **Same interruptibility**: stop ONE running agent from /runs (enter). The
    dispatch task is cancelled, the caller gets a plain "stopped by user"
    result, and the main turn survives and adapts.
  - The run_agent tool now owns the run lifecycle (register/cancel/finish) —
    it alone knows the dispatch id and holds the task; the turn worker only
    feeds steps. The name-aliasing workaround is gone.
  - **Esc no longer orphans subagents.** Cancelling the turn now explicitly
    cancels every in-flight dispatch task (awaiting a separate task does not
    propagate cancellation) — previously the subagent graph kept running in
    the background after a stop, spending tokens and mutating files, with the
    run stuck at "running".
- **Layout**: the live split is now 60% conversation / 40% agents; /runs uses
  the full terminal width (list 30% · selected run's log 70%).

## [0.12.1] — 2026-07

### Fixed
- **Subagent steps no longer vanish (panel stuck at "starting…").** The run
  was registered under the agent's NAME (its tool_call_id isn't knowable at
  registration), while live steps arrived keyed by the real id from the event
  tag — the resolver compared the id against names, matched nothing, and
  dropped every step. Resolution now binds the real id to the name-keyed run
  on first contact (aliasing); ambiguous matches (two parallel same-name
  runs) are dropped rather than misattributed.
- **Subagents get the background-process tools.** A definition listing
  start/check/stop_process silently lost them (they were main-graph-only), so
  an agent needing a dev server blocked its synchronous shell until timeout —
  a hung dispatch with no way to make progress. Full-tier and explicit-list
  subagents now get them (same self-gating, same /ps visibility, killed on
  app exit); read-only never.

## [0.12.0] — 2026-07

### Added
- **Live agent side panel.** While subagents run (and the terminal is ≥110
  cols), the main screen splits: conversation left, up to 4 running agents
  right — each pane a header (`⏵ name · 1m 42s · 9 steps`) plus the tail of
  its step log, soft dividers between agents, ticking every second. Collapses
  automatically when the last agent finishes; narrow terminals skip the split.
- **Footer agents chip.** `⏵ 2 agents /runs` appears while dispatches run;
  click it to open /runs.
- **/runs screen** — every dispatch this session, side by side: run list left
  (30%), the SELECTED run's timestamped step log right, tailing live; ↑/↓ or
  click to switch. Finished and failed runs stay reviewable.
- **First-class dispatch rows.** run_agent renders as `Agent <name> — <task>`
  (no more raw args dump); on completion the telemetry trailer becomes the
  rail (`14 tool calls · 82.3k tokens · $0.0210 · 192s`) with the agent's
  report in a collapsible body.

## [0.11.0] — 2026-07

### Added
- **Subagent tracing & telemetry.** Every `run_agent` dispatch now persists its
  full transcript (task, each model step + tool call/result, token/cost/
  duration summary) as JSONL under the conversation's `agents/` directory —
  the audit trail the main conversation deliberately omits. The tool result's
  trailer now carries real telemetry: `[agent: X · 14 tool calls · 82.3k
  tokens · $0.0210 · 192s]`. Trace writing is best-effort — it can never fail
  a dispatch.
- **Per-dispatch identity.** Subagent runs are tagged
  `visvoai_subagent:<name>:<tool_call_id>` (the id injected by the tool infra,
  never model-supplied) so parallel dispatches of the SAME agent are
  distinguishable — required for correct trace attribution and future
  per-row live traces.

## [0.10.1] — 2026-07

### Fixed
- **Subagent execution no longer leaks into the main conversation.** Nested
  graph events bubble through `astream_events`; a dispatched agent's every
  tool call and message was rendering as top-level conversation content AND
  being persisted into the thread as the main agent's own history (with a
  dangling `run_agent` call). Subagent runs are now tagged and filtered: the
  main view shows the `run_agent` row plus a live status pulse ("agent
  performance-validator: run_shell…"); the subagent's token usage still
  counts toward the turn. Same fix in headless single-shot output.
- **Subagents get real context.** They now run with the same per-turn context
  assembly as the main agent — environment (cwd), project instructions
  (AGENTS.md), git state. Previously they started blind, not even knowing the
  working directory.
- **Stale tool names in definitions are countered.** A definition prompt that
  hardcodes tool names (e.g. `chrome__*` MCP tools that aren't connected
  right now) made subagents call tools they don't have. Every subagent prompt
  now carries a tool-reality-check clause, and creation guidance tells the
  model to describe capabilities rather than hardcode tool names.

## [0.10.0] — 2026-07

### Added
- **MCP tools reach subagents.** Full-tier agents now get the session's
  connected MCP tools (gated exactly like at the top level), and explicit
  tool lists can select them by `server__tool` name. Never in `read-only` —
  a remote server's side effects can't be classified or sandboxed. An agent
  like a Lighthouse auditor referencing `chrome__*` tools now actually has
  them.

### Fixed
- **Pending agent approval is now impossible to miss.** When a turn creates a
  project agent (or you open the CLI in a repo that ships one), the app
  itself shows a warning toast pointing at /agents — deterministic, not
  dependent on the model remembering to mention it.
- **Better agent-creation guidance to the model**: pick the smallest tool
  tier that fits (read-only / explicit list / full), and explain usage to the
  user in plain language — run_agent is the model's internal tool, never a
  command the user types (a live response had presented it as one).

## [0.9.1] — 2026-07

### Fixed
- **Agent-created agents no longer vanish.** The main agent had no way to know
  the definition format, so "create me an agent" produced files the loader
  silently ignored (live incident: a `.toml` definition). The `run_agent` tool
  description now teaches the exact `.md` + frontmatter format, non-`.md`
  files in an agents directory are logged and flagged as a warning toast when
  `/agents` opens, and the loader behavior is otherwise unchanged.

## [0.9.0] — 2026-07

### Added
- **Agents & subagents.** The main agent can now delegate self-contained tasks
  via a `run_agent(agent, task)` tool. Two built-ins ship with the CLI:
  `explore` (fast read-only reconnaissance — reads, searches, and a shell that
  refuses writes and runs inside the OS no-write sandbox; zero approval
  prompts) and `general` (full tool set — mutations still ask you, exactly as
  at the top level). Independent dispatches run IN PARALLEL. Each subagent
  starts with a fresh, isolated context; only its final answer returns.
- **User-defined agents.** Drop a markdown file in `~/.visvoai/agents/`
  (personal) or `.visvoai/agents/` (project, shareable via the repo) —
  frontmatter sets description/tools/model, the body is the system prompt.
  Project-defined agents need one-time approval in `/agents` (recorded outside
  the repo; any edit re-prompts) — same trust model as project MCP servers.
- **`/agents` screen** — the merged roster with each agent's capability tier
  and model, plus trust approval for project agents.
- **`visvoai agents list/show/create/remove`** — manage agents headlessly;
  `create` is an interactive wizard. Or just ask the agent to write one — a
  definition is a plain file, created through the normal edit approval.

## [0.8.0] — 2026-07

### Added
- **Read/write shell gating with OS-level enforcement.** `run_shell` now
  classifies each command: read-only commands (ls, cat, grep, rg, find,
  git log/status/diff, docker ps, ...) run immediately — no approval prompt —
  inside an OS sandbox that denies file writes at the kernel (macOS
  `sandbox-exec`, Linux `bwrap`). Commands that can mutate prompt the user
  exactly as before. A write disguised as a read (interpreters, awk
  redirection, anything that fools the text classifier) is blocked by the
  kernel and rerouted through the approval prompt — the silent-write path
  does not exist. Platforms without a sandbox fall back to classifier-only
  gating (conservative: unknown verbs always prompt).

## [0.7.5] — 2026-07

### Changed
- **The connected look is back — with soft borders.** 0.7.4's vertical-free
  redesign is reverted: the wired tool spine (┌─/├─/└─), full table grids, the
  side-by-side diff divider, citation rails, and tree lines are all restored.
  Diagnosis concluded: Terminal.app renders STYLED box glyphs from the font
  (a hair short of the cell) while default-attribute text gets procedurally
  drawn perfect boxes — so every styled TUI (Claude Code's tables included) has
  the same hairline seams. Ours were only glaring because table grid lines were
  drawn at full strength; they're now 35% ($foreground) so the seams vanish
  into the line's softness. (0.7.4 remains in history if a spacing-proof mode
  is ever wanted as a config flag.)

## [0.7.3] — 2026-07

### Fixed
- **Theme persistence broke light terminals (0.7.2 regression).** Persisting the
  full theme name froze the light/dark mode, painting dark-theme text onto light
  terminal backgrounds ("barely able to see anything"). Only the PALETTE is a
  preference — the mode re-detects from the terminal background every launch,
  as it always did. Ctrl+T stays a session-level override.

## [0.7.2] — 2026-07

### Fixed
- **Preferences persist across launches.** Your theme (palette + light/dark) and
  your /model pick (model + thinking level) are saved and restored next time —
  previously every launch reset to the defaults. Stale prefs (a renamed theme,
  an uninstalled model) fall back gracefully instead of sticking or crashing.
- **A resumed conversation keeps ITS settings.** /resume and --resume now restore
  the conversation's own model + thinking level from its meta (with a notice and
  a graceful keep-current if that model is no longer available) — a chat started
  on one model no longer silently continues on another.
- The footer context gauge was invisible at 0% (its empty track sat on a
  background-colored panel); the track now uses the hover tint so the gauge
  always has a visible body.

## [0.7.1] — 2026-07

### Changed
- **/rewind reads like the chat.** The question picker is now chronological —
  oldest at the top, newest at the bottom — matching the direction the
  conversation itself scrolls, and opens with the newest question already
  selected (the likeliest rewind target). Same for the /branch and /fork
  checkpoint pickers, which share the screen.

## [0.7.0] — 2026-07

### Changed — UX polish (self-usable for new users)
- **One visual system.** A single icon vocabulary (`❯` active, `●` connected,
  `⏵` running, `✗` failed, `!` needs you, `◈` checkpoints/branches — `⎇` now means
  git only) and a 9-class output taxonomy: every block in the stream has one icon
  family, one accent, and one typography rule, documented as the convention for
  new widgets.
- **All 7 full-screen pages share one chrome** (title / subtitle / list / hint) with
  identical key-help formatting. Guidance where it was missing: Rewind explains
  nothing is lost until you choose; Branch clarifies branches are conversation-local
  (not git); Model surfaces its sort/filter chords; Sessions teaches search recovery.
- **The mouse works everywhere.** Slash-menu and @-file rows run/insert on click;
  the ◆ mode chip cycles approval mode on click; the ⏵ processes chip opens /ps;
  picker hints say enter/click. (Rows, thoughts, and diffs were already clickable.)
- **Editor-grade prompt editing.** Undo/redo (Ctrl+Z / Ctrl+Y), macOS Option-arrow
  and emacs alt+b/f word motions, alt+d delete-word-right — on top of the stock
  word-delete/kill-line/word-jump set. All documented in /help's new
  "Typing & editing" section.
- /help gains the editing section + a mouse note; the working-spinner tips now
  teach /mcp and /ps until you've used them.

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
