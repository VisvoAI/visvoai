"""VisvoApp — composes the visvoai TUI from reusable widgets.

Holds app-level layout/CSS, the shared turn primitives (begin/mount/tool-node,
HITL prompts), and the REAL agent turn (`_run_real_turn`, streaming live
`visvoai-core` output). The scripted mock `/demo` showcase lives in DemoMixin
(visvoai.cli/demo.py), mixed in below — kept separate so the real-agent
integration stays the focus. Each widget owns its own styling (DEFAULT_CSS).
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager

from rich.text import Text
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from visvoai.cli import agent, cli_changelog, gitio, store, theme
from visvoai.cli import state as state_mod
from visvoai.cli.mock import git_info
from visvoai.cli.widgets import (
    Form,
    FreeText,
    Plan,
    Selection,
    StatusBar,
    ToolGroup,
    ToolNode,
    SystemNote,
    UserMsg,
    Welcome,
    WelcomeBanner,
)
from visvoai.cli.agent_turn import AgentTurnMixin
from visvoai.cli.commands import CommandsMixin
from visvoai.cli.demo import DemoMixin
from visvoai.cli.render import RenderMixin
from visvoai.cli.rewind import RewindMixin
from visvoai.cli.sessions import SessionsMixin
from visvoai.cli.widgets.file_menu import FileMenu
from visvoai.cli.widgets.prompt import PromptArea
from visvoai.cli.widgets.slash import SlashMenu

# Pixel-block wordmark (pagga figlet), split so "VisvoAI" and "CLI" can be
# two-toned like the opencode logo. Generated once; embedded to avoid a dep.
_LOGO_VISVO = [
    "░█░█░▀█▀░█▀▀░█░█░█▀█░█▀█░▀█▀",
    "░▀▄▀░░█░░▀▀█░▀▄▀░█░█░█▀█░░█░",
    "░░▀░░▀▀▀░▀▀▀░░▀░░▀▀▀░▀░▀░▀▀▀",
]
_LOGO_CLI = [
    "░█▀▀░█░░░▀█▀",
    "░█░░░█░░░░█░",
    "░▀▀▀░▀▀▀░▀▀▀",
]

class VisvoApp(DemoMixin, AgentTurnMixin, SessionsMixin, CommandsMixin, RewindMixin, RenderMixin, App):
    TITLE = "visvoai"
    ENABLE_COMMAND_PALETTE = False

    # App-level layout only — component styling lives on each widget.
    CSS = """
    /* App/Screen background is set imperatively to the detected terminal color
       (see _apply_background) so the UI blends with the terminal. Cards are
       borderless + transparent so that one background shows through. */
    Screen { border: none; padding: 0; }

    #log {
        height: 1fr;
        padding: 1 0;
        scrollbar-size: 0 0;   /* hidden bar; mouse-wheel / PgUp still scroll */
    }
    /* Dock the input region to the bottom so adding/removing the slash menu
       above the prompt never shifts the prompt's screen position. */
    #bottom { dock: bottom; height: auto; padding: 0; }
    /* Pinned plan region: empty (collapses) until a turn pins its live plan. */
    #pinned { height: auto; }
    /* Input row: a "❯" marker + the prompt, with top/bottom rules spanning both. */
    #prompt-row {
        height: auto;
        border-top: solid $primary;
        border-bottom: solid $primary;
    }
    #prompt-marker { width: 2; color: $primary; padding: 0 1 0 0; }
    .quit-hint {
        color: $warning;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }
    /* Context-almost-full nudge: floats just above the input, right-aligned. */
    #ctx-warning {
        color: $warning;
        height: 1;
        padding: 0 1;
        content-align: right middle;
        text-align: right;
    }
    /* Faint hairline separating one turn from the next (minimal layout). One blank
       above it; the UserMsg's own top margin gives the blank below — a single,
       symmetric breath at the turn boundary, the only airiness in the stack. */
    
    /* One blank line before a block when the block CATEGORY changes (COT / answer /
       tool / note / plan / error / hitl). Consecutive tool calls stay flush as a
       cluster. Flush within a group, a single gap between groups → readable + compact. */
    .blk-gap { margin-top: 1; }
    """

    BINDINGS = [
        Binding("ctrl+t,super+t", "toggle_mode", "Theme", key_display="Ctrl+T"),
        # priority: the focused prompt (a TextArea) otherwise swallows shift+tab
        # (its default is focus-previous), so the App must intercept it first.
        Binding("shift+tab", "cycle_hitl_mode", "Mode", priority=True, key_display="⇧Tab"),
        Binding("pageup", "scroll_up", "Scroll", priority=True, key_display="PgUp"),
        Binding("pagedown", "scroll_down", "Scroll", priority=True, show=False),
        Binding("ctrl+up,super+up", "scroll_up", "Scroll", priority=True, show=False),
        Binding("ctrl+down,super+down", "scroll_down", "Scroll", priority=True, show=False),
        Binding("ctrl+q,super+q", "request_quit", "Quit", key_display="Ctrl+Q"),
        Binding("ctrl+c,super+c", "request_quit", "Quit", show=False),
        Binding("ctrl+k,super+k", "request_clear", "Clear", show=False),
        Binding("ctrl+r,super+r", "open_sessions", "Sessions", show=False),
        Binding("ctrl+g,super+g", "open_git", "Git", show=False),
        Binding("ctrl+b,super+b", "open_rewind", "Rewind", show=False),
    ]

    def __init__(self, term_bg: str | None = None, model: str | None = None,
                 resume: str | None = None) -> None:
        super().__init__()
        self._git = git_info()
        self._cwd = os.getcwd()
        # Deferred startup actions (emitted/run in on_mount, once the app is up).
        self._startup_notices: list[str] = []
        self._startup_resume = resume   # conversation id | "__last__" | None
        self._model = self._resolve_startup_model(model)
        # Thinking level for the active model — starts at its declared default; the
        # model page lets the user change it. None when the model can't think.
        _dv = agent.deployment_view(self._model)
        self._thinking = _dv.default_thinking if _dv else None
        # Saved thinking pref applies only when it belongs to the saved model —
        # a level saved for model A must not leak onto model B's capabilities.
        if state_mod.get_pref("model") == self._model:
            saved_think = state_mod.get_pref("thinking", self._thinking)
            if saved_think is None or (_dv and saved_think in (_dv.thinking_levels or [])):
                self._thinking = saved_think
        # Real conversation history (LangChain messages) for multi-turn turns.
        self._history: list = []
        # File-based persistence (resolved lazily on first save / resume — no
        # side effects at construction so tests never touch the store).
        self._project_id: str | None = None
        self._conv_id: str | None = None
        # How many messages of _history are already on disk — the JSONL log appends
        # only the tail beyond this each turn (set to the loaded length on resume).
        self._persisted_count = 0
        # The one-shot LLM title runs once per conversation (set True on resume —
        # an existing thread already has its title).
        self._title_generated = False
        # Cumulative conversation cost (USD), shown in the footer; summed from saved
        # receipts on resume. UI/budget signal only — not in model context.
        self._conv_cost = 0.0
        # Permission gate: mutating tools ask before acting. The HITL mode
        # (shift+tab / /mode) relaxes WHEN it asks; "allow all this session"
        # accumulates per-tool in _approved_all; the config-driven policy
        # pre-authorizes known-safe ops. Session-only — resets to NORMAL each launch.
        from visvoai.cli.hitl_modes import HITLMode
        from visvoai.cli.permissions import load_policy
        self._hitl_mode = HITLMode.NORMAL
        self._approved_all: set[str] = set()
        self._policy = load_policy(self._cwd)
        # ToolNode runs concurrent tool_calls in parallel; this serializes their
        # approval prompts so two Selections can't mount/contend at once.
        self._hitl_lock = asyncio.Lock()
        # Background processes (dev servers, watchers) started by the agent —
        # app-level so they survive across turns; ALL killed on app exit so a
        # closed CLI never leaves a server squatting on a port.
        from visvoai.cli.processes import ProcessRegistry
        self._processes = ProcessRegistry()
        # Git-structured history (cli-git-structure): a shadow repo snapshots the work
        # tree per tool-batch + turn-end, linked to the thread by message index so code
        # and conversation rewind together. All lazy + best-effort — never breaks a turn.
        self._checkpoints = None              # ShadowRepo | None (built lazily)
        self._cp_failed = False               # git missing / init failed → stop retrying
        self._cp_branch = "main"              # active conversation branch
        self._cp_tip_id: str | None = None    # active branch tip (checkpoint id)
        self._cp_tip_sha: str | None = None   # active branch tip (shadow commit sha)
        self._cp_turn_label = ""              # current turn's prompt snippet (checkpoint label)
        self._ctx_pct: int | None = None  # context % — hidden until a real turn reports usage
        self._ctx_tokens: int | None = None  # raw tokens in context (footer label)
        self._pace = 1.0    # demo speed multiplier (tests set this low to run fast)
        self._turns = 0       # turns rendered this session (drives the turn hairline)
        self._hitl_active = False  # a HITL owns the input area (suppresses the pinned plan)
        self._quitting = False
        self._clearing = False
        # User input submitted while a turn is running is queued here (a redirect),
        # not discarded — the turn worker reconciles with it. See Case B Turn 6.
        self._pending_redirect: str | None = None
        # The open tool wire-group: consecutive tool calls join one ToolGroup so
        # their connectors link. Cleared whenever a non-tool block (or a HITL) lands.
        self._tool_group = None
        # Detected terminal background ('#rrggbb') to blend with, or None →
        # transparent (Textual flattens to black; fine on dark terminals).
        self._term_bg = term_bg
        # Register the shared brand themes (6 palettes × light/dark) and start in the
        # light/dark MODE that matches the terminal (from its detected bg luminance),
        # so text is legible on light terminals too — not just dark. Ctrl+T flips it.
        for t in theme.THEMES:
            self.register_theme(t)
        # The PALETTE is a preference; light/dark MODE is a property of the
        # terminal we're launched in (detected from its background) — persisting
        # the mode painted dark-theme text onto light terminals. Recombine.
        saved_palette = state_mod.get_pref("palette")
        pal = saved_palette if saved_palette in theme.PALETTES else theme.DEFAULT_PALETTE
        self.theme = theme.theme_name(pal, theme.mode_for_bg(self._term_bg))

    # ── layout ──────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="log"):
            yield WelcomeBanner(self._welcome_left, self._welcome_right)
        with Vertical(id="bottom"):
            # Active plan/todo, pinned just above the input so it never scrolls away.
            yield Vertical(id="pinned")
            with Horizontal(id="prompt-row"):
                yield Static("❯", id="prompt-marker")
                yield PromptArea(id="prompt")
            yield StatusBar(self._model, self._status_location(), id="status")

    def _resolve_startup_model(self, requested: str | None) -> str:
        """The model to start on: an explicit --model wins, then the user's saved
        preference (from the last /model pick), then the registry default. Unknown
        ids fall through to the next tier (stale prefs must not crash or stick)."""
        if requested is None:
            saved = state_mod.get_pref("model")
            if saved and agent.deployment_view(saved) is not None:
                requested = saved
        try:
            default = agent.default_chat_model()
        except Exception:
            default = "gemini-2.5-flash"
        if not requested:
            return default
        if requested in {mid for mid, _ in agent.chat_models()}:
            return requested
        self._startup_notices.append(f"unknown model '{requested}' — using {default}")
        return default

    async def on_unmount(self) -> None:
        """App teardown — kill every background process group the agent started
        and close live MCP sessions. Runs on quit, Ctrl+C, and crash-teardown
        alike; without it a closed CLI leaves dev servers running on their ports.
        (Stdio MCP children also die with the process — pipe EOF — as a backstop.)"""
        self._processes.stop_all(by="shutdown")
        from visvoai.cli.mcp import close_mcp_sessions
        await close_mcp_sessions()

    def on_mount(self) -> None:
        self._apply_background()
        # The scroll log shouldn't take focus on click — keep the prompt focused.
        self.query_one("#log", VerticalScroll).can_focus = False
        self.query_one("#status", StatusBar).set_context(self._ctx_pct, self._ctx_tokens)
        self._refresh_model_status()
        # Background-process chip: poll cheaply so the footer reflects processes the
        # agent starts/stops mid-turn (and ones that exit on their own).
        self.set_interval(2.0, self._refresh_process_chip)
        self.set_tab_title(None)   # brand-only until a conversation has a title
        self.query_one("#prompt", PromptArea).focus()
        for msg in self._startup_notices:
            self.notify(msg)
        if self._startup_resume is not None:
            self.run_worker(self._startup_resume_flow())
        # Surface "what's new in this version" below the welcome banner on launch
        # (skipped on /clear — the panel was already shown & marked-seen at first
        # launch, and /clear intentionally gives a blank slate).
        self._maybe_mount_changelog_panel()
        self._maybe_launch_scan()

    # Context fill at/above this %, warn the user to compact or switch models.
    CTX_WARN_PCT = 85

    def _set_context(self, pct: int | None, tokens: int | None = None) -> None:
        """Update the context gauge. pct None → hide it (e.g. a fresh conversation)."""
        self._ctx_pct = None if pct is None else max(0, min(100, pct))
        self._ctx_tokens = None if pct is None else tokens
        sb = self._status_bar()
        if sb is None:
            return   # teardown race (cancelled turn) — see _status_bar
        sb.set_context(self._ctx_pct, self._ctx_tokens)
        self.run_worker(self._update_ctx_warning())

    async def _update_ctx_warning(self) -> None:
        """Float a nudge above the input when context is nearly full; remove it once
        there's headroom again."""
        bottom = self.query_one("#bottom", Vertical)
        existing = bottom.query("#ctx-warning")
        if self._ctx_pct is not None and self._ctx_pct >= self.CTX_WARN_PCT:
            text = (f"⚠ Context {self._ctx_pct}% full — /compact, or switch to a "
                    f"larger-window model")
            if existing:
                existing.first().update(text)
            else:
                await bottom.mount(Static(text, id="ctx-warning"),
                                   before=self.query_one("#prompt-row", Horizontal))
        elif existing:
            await existing.remove()

    def set_tab_title(self, conversation_title: str | None) -> None:
        """Set the terminal/tab title to 'VisvoAI | <conversation>' via the OSC
        escape (Textual's .title only drives the in-app header). None → just the
        brand. Wrapped so a terminal that ignores OSC can never break a turn."""
        brand = "VisvoAI"
        text = f"{brand} | {conversation_title}" if conversation_title else brand
        try:
            if sys.stdout.isatty():   # only a real terminal honors OSC; skip under test capture
                sys.stdout.write(f"\033]0;{text}\007")
                sys.stdout.flush()
        except Exception:
            pass

    def _status_location(self) -> str:
        # Full path (home contracted to ~) so the footer shows WHERE you are, not
        # just the leaf dir — important when several repos share a folder name.
        home = os.path.expanduser("~")
        path = self._cwd
        if path.startswith(home):
            path = "~" + path[len(home):]
        return f"{path}  ⎇ {self._git}" if self._git else path

    def _status_bar(self) -> StatusBar | None:
        """The footer StatusBar, or None during teardown. A turn worker's finally
        block (cancel/quit mid-turn) races widget unmount — a footer update must
        degrade to a no-op then, not crash the worker with NoMatches."""
        try:
            return self.query_one("#status", StatusBar)
        except NoMatches:
            return None

    def _set_status(self, text: str | None) -> None:
        sb = self._status_bar()
        if sb is not None:
            sb.set_status(text)

    def _update_cost_status(self) -> None:
        """Push the cumulative conversation cost to the footer."""
        sb = self._status_bar()
        if sb is not None:
            sb.set_cost(self._conv_cost)

    def _refresh_model_status(self) -> None:
        """Paint the footer's idle model line from the active model + thinking level."""
        dv = agent.deployment_view(self._model)
        sb = self.query_one("#status", StatusBar)
        if dv:
            sb.set_model_line(dv.display_name, self._thinking, dv.in_cost, dv.out_cost)
        else:
            sb.set_model(self._model)

    def _apply_background(self) -> None:
        """Paint the App + Screen with the detected terminal color (seamless), or
        transparent when unknown. Re-applied after a theme switch, which otherwise
        resets the background to the theme's own."""
        value = self._term_bg or "transparent"
        self.styles.background = value
        self.screen.styles.background = value

    # ── theming ──────────────────────────────────────────────────────────────
    def _apply_theme(self, name: str) -> None:
        """Switch theme. Textual re-resolves CSS automatically; we also nudge
        Rich render()/restyle widgets so baked-in text colors follow. The choice
        is saved as a user preference — the next launch starts on its PALETTE
        (mode re-detects from the terminal; ctrl+T stays session-only)."""
        self.theme = name
        state_mod.set_pref("palette", theme.parse_theme(name)[0])
        self._apply_background()  # theme switch resets bg → re-paint terminal color
        for widget in self.screen.query("*"):
            restyle = getattr(widget, "restyle", None)
            if restyle is None:
                widget.refresh()
            elif asyncio.iscoroutinefunction(restyle):
                self.run_worker(restyle())
            else:
                restyle()

    def action_toggle_mode(self) -> None:
        """Ctrl+T — flip the current palette between light and dark."""
        palette, mode = theme.parse_theme(self.theme)
        new_mode = "light" if mode == "dark" else "dark"
        self._apply_theme(theme.theme_name(palette, new_mode))
        self.notify(f"theme: {palette} · {new_mode}")

    def on_status_bar_mode_chip_clicked(self, _msg) -> None:
        """Mouse parity: clicking the ◆ mode chip cycles the approval mode."""
        self.action_cycle_hitl_mode()

    def on_status_bar_procs_chip_clicked(self, _msg) -> None:
        """Mouse parity: clicking the ⏵ processes chip opens /ps."""
        self.run_worker(self._ps_flow())

    def action_cycle_hitl_mode(self) -> None:
        """Shift+Tab (and /mode) — cycle the approval mode: normal → auto-edit →
        accept-all. Relaxes WHEN the gate asks; path confinement is unaffected.
        The active mode shows as the status-bar chip — no toast needed."""
        self._hitl_mode = self._hitl_mode.next()
        state_mod.record_used("mode")
        self.query_one("#status", StatusBar).set_mode(self._hitl_mode.chip)

    def notify(self, message: str, *, severity: str = "information", **kwargs) -> None:
        """Suppress info-level toasts — they were noise (every theme/model/mode/resume
        action popped one); state lives in the status bar and inline UI instead.
        warning/error toasts still show, so boundary failures are never silenced."""
        if severity == "information":
            return
        super().notify(message, severity=severity, **kwargs)

    # ── model picker / sessions ───────────────────────────────────────────────
    def _tv(self, key: str) -> str:
        return self.theme_variables[key]

    def _welcome_left(self) -> Text:
        primary, fg, muted = self._tv("primary"), self._tv("foreground"), self._tv("muted")
        t = Text()
        for visvo, cli in zip(_LOGO_VISVO, _LOGO_CLI):
            t.append(visvo, style=primary)   # brand color on "VisvoAI"
            t.append("  ")
            t.append(cli, style=fg)          # brighter on "CLI" (opencode-style)
            t.append("\n")
        t.append("\nyour terminal coding agent", style=muted)
        return t

    def _welcome_right(self) -> str:
        """Right column of the welcome banner. Varies by launch state: a brand-new
        project gets the heavy onboarding copy; a returning-but-empty project gets
        a lighter nudge; an existing conversation (or --resume) keeps the
        standard 'what is this' copy."""
        state = self._launch_state()
        if state == "onboarding":
            return self._welcome_onboarding()
        if state == "empty":
            return self._welcome_empty()
        return self._welcome_standard()

    # Launch state determines which welcome copy shows. Pure read of project state
    # — does not write the project anchor (resolve_project_id does that lazily on
    # the first turn; we want a fresh visitor to see the onboarding, not be told
    # "welcome back" before they've done anything).
    def _launch_state(self) -> str:
        # --resume always lands on existing history → standard copy.
        if self._startup_resume is not None:
            return "standard"
        pid = store.find_project_id(self._cwd)
        if pid is None:
            return "onboarding"        # no .visvoai/config.toml anywhere → first time
        if store.has_conversations(pid):
            return "standard"          # history exists
        return "empty"                 # project exists but no conversations yet

    # Rotating input placeholders (#5) — a blank prompt suggests what's possible.
    _PROMPT_EXAMPLES = (
        "Describe a task, ask a question, or @mention a file…",
        "try: fix the failing test in tests/",
        "try: refactor auth.py to use dataclasses",
        "try: add tests for the payment module",
        "try: explain how the request flow works here",
        "try: find and remove dead code",
        "try: summarize what changed on this branch",
    )

    def _rotate_placeholder(self) -> None:
        """Advance the prompt's placeholder to the next example (called after each turn
        and after /clear). Best-effort — a terminal that ignores it just keeps the last."""
        self._placeholder_i = (getattr(self, "_placeholder_i", 0) + 1) % len(self._PROMPT_EXAMPLES)
        try:
            self.query_one("#prompt", PromptArea).placeholder = self._PROMPT_EXAMPLES[self._placeholder_i]
        except Exception:
            pass

    def _welcome_standard(self) -> str:
        """The original copy: assumes the user knows what visvoai is."""
        secondary, fg = self._tv("secondary"), self._tv("foreground")
        return (
            f"[{fg}]I read & edit files, run commands, and stream changes — "
            "you approve anything that touches your code.[/]\n\n"
            "[dim]try:[/]\n"
            f"  [{secondary}]›[/] add an anthropic provider to my config\n"
            f"  [{secondary}]›[/] find and fix the failing test\n\n"
            f"[dim]type[/] [b {secondary}]/[/][dim] for commands (try /help)[/]"
        )

    def _welcome_onboarding(self) -> str:
        """First-time welcome: the user has never launched visvoai in this directory
        (no .visvoai/config.toml anywhere up the tree). Heavier guidance — what
        this is, what to try, and the auto-checkpoint / time-travel hook so the
        unique capability is visible from the very first screen."""
        secondary, primary, fg, muted = (self._tv("secondary"), self._tv("primary"),
                                        self._tv("foreground"), self._tv("muted"))
        return (
            f"[{fg}]Welcome — let's start.[/]\n"
            f"[{muted}]I read & edit files and run commands; you approve anything "
            f"that touches your code.[/]\n\n"
            f"[dim]try:[/]\n"
            f"  [{secondary}]›[/] fix the failing test in tests/\n"
            f"  [{secondary}]›[/] add an anthropic provider to my config\n"
            f"  [{secondary}]›[/] refactor auth.py to use dataclasses\n\n"
            f"[dim]type[/] [b {secondary}]/[/][dim] for commands · [/]"
            f"[b {secondary}]/help[/][dim] to learn · [/]"
            f"[b {secondary}]/tour[/][dim] for a 60-second walkthrough[/]\n"
            f"[dim]type[/] [b {secondary}]@file[/][dim] to attach a file[/]\n\n"
            f"[{muted}]every turn auto-saves a checkpoint — "
            f"[b {primary}]/rewind[/] to undo, "
            f"[b {primary}]/branch[/] to fork.[/]"
        )

    def _welcome_empty(self) -> str:
        """Returning user, but no conversations yet (either a project was created
        then abandoned, or `/clear` was just pressed). Lighter than onboarding —
        they already know what visvoai is; they just need a nudge to start."""
        secondary, primary, fg, muted = (self._tv("secondary"), self._tv("primary"),
                                        self._tv("foreground"), self._tv("muted"))
        return (
            f"[{fg}]Welcome back — no conversations here yet.[/]\n"
            f"[{muted}]Type to start a chat, or "
            f"[b {primary}]/resume[/] to reopen an old one.[/]\n\n"
            f"[dim]try:[/]\n"
            f"  [{secondary}]›[/] summarize this repo's structure\n"
            f"  [{secondary}]›[/] add tests for the auth module\n\n"
            f"[dim]type[/] [b {secondary}]/[/][dim] for commands · "
            f"[b {primary}]/help[/] [dim]for the full list[/]"
        )

    # ── proactive launch scan (#7) ────────────────────────────────────────────
    def _maybe_launch_scan(self) -> None:
        """One quiet, actionable line at launch if the repo has uncommitted changes —
        so a returning user is oriented ('you left N changes here') with a next step.
        Diff-free (status_summary), git-repo-only, silent when clean or not a repo."""
        if self.is_headless:
            return   # don't do real-git startup I/O under test / headless runs
        try:
            status = gitio.status_summary(self._cwd)
        except Exception:
            return
        files = (status or {}).get("files") or []
        if not files:
            return
        n = len(files)
        log = self.query_one("#log", VerticalScroll)
        log.mount(SystemNote(
            f"{n} uncommitted change{'s' if n != 1 else ''} in this repo — "
            f"/commit (Ctrl+G) to review, or just tell me what to change", kind="info"))
        log.scroll_end(animate=False)

    # ── changelog "what's new" panel ──────────────────────────────────────────
    def _maybe_mount_changelog_panel(self) -> None:
        """Mount a single-line 'what's new' card below the welcome banner when
        there are CHANGELOG entries newer than the user's `last_seen_version`.
        Skipped when no project anchor exists (the first-ever launch in a brand
        new directory — the banner's onboarding copy is already enough) and
        skipped when there's nothing new (no point flashing it on every launch)."""
        pid = store.find_project_id(self._cwd)
        if pid is None:
            return
        state = state_mod.get_state(pid)
        last_seen = state.get("last_seen_version")
        entries = cli_changelog.new_since(last_seen)
        if not entries:
            return
        log = self.query_one("#log", VerticalScroll)
        log.mount(Welcome(lambda: self._changelog_markup(entries, last_seen)))
        log.scroll_end(animate=False)
        # Mark this version as seen so the panel doesn't re-appear next launch
        # (until the next version bump adds a newer entry).
        try:
            state_mod.update_state(pid, last_seen_version=cli_changelog.current_version())
        except OSError:
            pass   # best-effort — a failed write just means we re-show next launch

    def _changelog_markup(self, entries: list[dict], last_seen: str | None) -> str:
        """The 'what's new' panel markup: one muted line per new entry, plus a
        heading. Kept compact — the user is at the welcome screen, not reading
        a release note."""
        primary, secondary, muted = (self._tv("primary"), self._tv("secondary"),
                                     self._tv("muted"))
        if last_seen is None:
            heading = f"[b {primary}]what's new in visvoai {cli_changelog.current_version()}[/]"
        else:
            heading = (f"[b {primary}]what's new since {last_seen}[/] "
                       f"[{muted}]({len(entries)} entr{'y' if len(entries) == 1 else 'ies'})[/]")
        lines = [heading, ""]
        for e in entries:
            summary = cli_changelog.one_line_summary(e)
            lines.append(
                f"  [{secondary}]v{e['version']}[/] [{muted}]· {e['date']}[/]  "
                f"[{muted}]—[/] {summary}"
            )
        return "\n".join(lines)

    # ── slash commands ───────────────────────────────────────────────────────
    # ── clear confirm (Ctrl+K twice within 2s) ───────────────────────────────
    # ── scrolling ───────────────────────────────────────────────────────────
    def action_scroll_up(self) -> None:
        self.query_one("#log", VerticalScroll).scroll_page_up()

    def action_scroll_down(self) -> None:
        self.query_one("#log", VerticalScroll).scroll_page_down()

    # ── inline HITL helper ──────────────────────────────────────────────────
    async def ask_choice(self, prompt: str, options: list[str], recommended: int = 0,
                         connected: bool = False, compact: bool = False):
        log = self.query_one("#log", VerticalScroll)
        with self._hidden_prompt():
            sel = Selection(prompt, options, recommended, compact=compact)
            if connected:
                # Tool approval: sit flush under the diff as one group (no gap).
                await log.mount(sel)
                log.scroll_end(animate=False)
            else:
                await self._mount_block(log, sel, "hitl")
            idx, note = await sel.ask()
            await sel.remove()
        return idx, note

    async def ask_form(self, prompt: str, fields: list[tuple[str, str, str]]):
        log = self.query_one("#log", VerticalScroll)
        with self._hidden_prompt():
            form = Form(prompt, fields)
            await self._mount_block(log, form, "hitl")
            values = await form.ask()
            await form.remove()
        return values

    async def ask_text(self, prompt: str, placeholder: str = "",
                       multiline: bool = True) -> str | None:
        log = self.query_one("#log", VerticalScroll)
        with self._hidden_prompt():
            ft = FreeText(prompt, placeholder, multiline)
            await self._mount_block(log, ft, "hitl")
            result = await ft.ask()
            await ft.remove()
        return result

    @contextmanager
    def _hidden_prompt(self):
        """Hide the main input row while a HITL is active; restore + focus after,
        so the HITL owns focus and the input never competes with it."""
        row = self.query_one("#prompt-row", Horizontal)
        row.display = False
        self._hitl_active = True
        self._tool_group = None   # a HITL breaks the tool wire-group
        self._update_pinned()   # HITL active → hide the pinned plan
        try:
            yield
        finally:
            row.display = True
            self._hitl_active = False
            self._update_pinned()   # HITL done → restore the pinned plan
            self.query_one("#prompt", PromptArea).focus()

    async def _begin_turn(self, log: VerticalScroll, user_text: str) -> None:
        """Open a turn by mounting the user anchor. This is the minimal-layout
        turn structure."""
        self._turns += 1
        await log.mount(UserMsg(user_text))
        self._last_kind = None  # first block under the anchor is flush (no gap)
        log.scroll_end(animate=False)

    async def _pin_plan(self, plan: Plan) -> None:
        """Dock the live plan just above the input so it stays visible as the turn
        works — instead of scrolling away in the conversation."""
        pinned = self.query_one("#pinned", Vertical)
        await pinned.remove_children()
        plan.add_class("pinned")
        await pinned.mount(plan)
        self._update_pinned()

    async def _unpin_plan(self) -> None:
        await self.query_one("#pinned", Vertical).remove_children()

    def _update_pinned(self) -> None:
        """The above-input slot shows ONE thing by priority: HITL > slash menu > plan.
        HITL and the slash menu never co-occur (a HITL hides the prompt), so the
        pinned plan is simply suppressed whenever either is present."""
        suppress = self._hitl_active or bool(self.query(SlashMenu)) or bool(self.query(FileMenu))
        self.query_one("#pinned", Vertical).display = not suppress

    async def _mount_block(self, log: VerticalScroll, widget, kind: str):
        """Mount one conversation block, inserting a 1-line gap when the block
        CATEGORY changes — except a run of consecutive tool calls, which stay flush
        as a cluster. This is the readable-but-compact rhythm: tight within a group,
        one breath between groups (COT vs answer vs tool cluster vs plan vs …)."""
        last = getattr(self, "_last_kind", None)
        if last is not None and not (kind == "tool" and last == "tool"):
            widget.add_class("blk-gap")
        # A non-tool block breaks the current tool wire-group.
        if kind != "tool":
            self._tool_group = None
        await log.mount(widget)
        self._last_kind = kind
        log.scroll_end(animate=False)
        return widget

    async def _tool_node(self, log: VerticalScroll, name: str, args: str,
                         rail: str = "") -> ToolNode:
        """Add a tool node to the active wire-group, opening a new group when the
        previous block wasn't a tool. Consecutive tools share one ToolGroup so the
        ├─/└─ connectors link them into one cluster."""
        if self._tool_group is None or getattr(self, "_last_kind", None) != "tool":
            group = ToolGroup()
            await self._mount_block(log, group, "tool")
            self._tool_group = group
        node = ToolNode(name, args, rail)
        await self._tool_group.add(node)
        return node

    # ── /demo picker — choose a case to run ──────────────────────────────────
    # ── Case A — cross-module refactor (breadth: plan mutation, auto-apply,
    #    stale-read, compaction, multi-file review) ───────────────────────────
    # ── Case C — feature build w/ mid-task redirection (plan mode, ordering
    #    deps, reconciliation, supersede/branch, clarification loop) ───────────
    # ── Case E — incident hotfix (large paste, diagnosis reply, worktree,
    #    expedited approval, narrow-scope interrupt, cross-branch) ─────────────
    # ── Case F — greenfield scaffold (mixed HITL, structure tree, file
    #    creation, ordered generation, long shell) ────────────────────────────
    # ── Case G — dependency upgrade (citation, semantic auto-apply, connected
    #    error, severity output, plan survives compaction) ────────────────────
    # Blocking HITL demos run in a WORKER, never inline in the action/message
    # pump — awaiting `ask_*` on the pump deadlocks (the keypress that would
    # resolve the future can't be processed). The flow body is the worker.
    # ── quit confirm (Ctrl+Q within 2s to exit; no escape) ───────────────────
    async def action_request_quit(self) -> None:
        if self._quitting:
            # Second Ctrl+Q within window → exit. Cancel the revert timer.
            self._cancel_quit_timer()
            self.exit()
            return

        self._quitting = True
        bottom = self.query_one("#bottom", Vertical)
        # Hide (don't destroy) the prompt row so its input history survives a cancel.
        self.query_one("#prompt-row", Horizontal).display = False
        await bottom.mount(
            Static("Press Ctrl+Q again to quit", classes="quit-hint", id="quit-hint"),
            before=self.query_one("#status", StatusBar),
        )
        self.set_focus(None)
        # 2-second window; if no second Ctrl+Q, revert to the input prompt.
        self._quit_timer = self.set_timer(2.0, self._revert_quit_hint)

    def _cancel_quit_timer(self) -> None:
        """Stop the revert timer if pending. Idempotent."""
        timer = getattr(self, "_quit_timer", None)
        if timer is not None:
            timer.stop()
            self._quit_timer = None

    def _revert_quit_hint(self) -> None:
        self._quit_timer = None
        if not self._quitting:
            return  # already reverted
        self._quitting = False
        self.run_worker(self._restore_input())

    async def _restore_input(self) -> None:
        hint = self.query("#quit-hint")
        if hint:
            await hint.remove()
        self.query_one("#prompt-row", Horizontal).display = True
        self.query_one("#prompt", PromptArea).focus()
