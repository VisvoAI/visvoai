"""
commands.py — CommandsMixin: the slash-command menu and its flows.

Owns /theme, /model (registry-driven, connected-providers-first), /compact,
/clear, /help and the slash-menu plumbing (show/filter/navigate/run). Mixed into
VisvoApp; pickers reuse ask_choice and demo actions via self.
"""
from __future__ import annotations

import difflib
import re

from textual.containers import Horizontal, Vertical, VerticalScroll

from visvoai.cli import agent, gitio, state, theme
from visvoai.cli.widgets import (
    CompactionMarker, Welcome, WelcomeBanner,
)
from visvoai.cli.screens import ModelScreen
from visvoai.cli.widgets.file_menu import FileMenu
from visvoai.cli.widgets.prompt import PromptArea
from visvoai.cli.widgets.slash import SlashMenu

# An @-mention being typed: an "@frag" at the end of the input, preceded by start
# or whitespace (so e-mails / decorators like "a@b" don't trigger the picker).
_MENTION_RE = re.compile(r"(?:^|\s)@(\S*)$")

# Slash commands: (name, description). Dispatched in run_command.
# The mock showcase (demo/choice/form/error/output) is intentionally NOT listed —
# its DemoMixin code is kept for tests but unreachable from the menu or by typing
# /demo (the menu only dispatches names present here), so it never ships to users.
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("help", "How it works — keys, commands & time-travel explained"),
    ("tour", "Take a 60-second guided walkthrough"),
    ("model", "Switch the AI model (and thinking depth)"),
    ("login", "Add a provider API key to unlock more models"),
    ("resume", "Reopen a past conversation in this project"),
    ("rewind", "Undo: restore your files & chat to an earlier point"),
    ("branch", "Switch between saved timelines of this chat"),
    ("fork", "Open a checkpoint in a new folder to explore in parallel"),
    ("export", "Save this chat as a shareable transcript or bundle"),
    ("log", "List this timeline's checkpoints (undo points)"),
    ("compact", "Summarize older turns to free up context"),
    ("mode", "Change when I ask before editing (normal/auto-edit/accept-all)"),
    ("commit", "Review changes & make a git commit"),
    ("theme", "Pick a color palette (Ctrl+T toggles light/dark)"),
    ("clear", "Start a fresh conversation"),
    ("quit", "Exit visvoai"),
]

# Grouping for /help (purely presentational — the menu above stays flat for search).
_HELP_GROUPS: list[tuple[str, list[str]]] = [
    ("Chat", ["model", "login", "mode", "compact", "clear"]),
    ("Time travel — your work is checkpointed every turn",
     ["rewind", "branch", "fork", "log", "export"]),
    ("Project", ["resume", "commit", "theme", "quit"]),
]

def _closest_command(fragment: str) -> str | None:
    """The nearest real command name to a mistyped `fragment` (e.g. 'undo' → 'rewind'
    by alias, 'reset'→'rewind' by fuzz), or None if nothing is close. Pure/testable."""
    names = [n for n, _ in SLASH_COMMANDS]
    # Hand-picked aliases: intent words users try that aren't the literal command.
    aliases = {"undo": "rewind", "revert": "rewind", "back": "rewind",
               "checkout": "branch", "switch": "branch", "timeline": "branch",
               "share": "export", "save": "export", "history": "log",
               "commands": "help", "keys": "help", "?": "help",
               "exit": "quit", "restart": "clear", "reset": "clear",
               "models": "model", "key": "login", "apikey": "login"}
    if fragment in aliases:
        return aliases[fragment]
    match = difflib.get_close_matches(fragment, names, n=1, cutoff=0.6)
    return match[0] if match else None


# (key, what it does) — the always-on shortcuts, surfaced in /help.
_HELP_KEYS: list[tuple[str, str]] = [
    ("Ctrl+B", "Rewind — open the undo / branch picker"),
    ("Ctrl+R", "Resume a past conversation"),
    ("Ctrl+G", "Review changes & commit (git)"),
    ("Shift+Tab", "Cycle approval mode (normal / auto-edit / accept-all)"),
    ("Ctrl+T", "Toggle light / dark"),
    ("Ctrl+K", "Clear (twice) — start fresh"),
    ("Ctrl+Q", "Quit (twice)"),
    ("PgUp / PgDn", "Scroll the conversation"),
    ("Esc", "Stop the current turn"),
]


class CommandsMixin:
    """Slash-command menu + the /theme, /model, /compact, /clear, /help flows."""


    async def _theme_picker_flow(self) -> None:
        """`/theme` — pick a brand palette (keeps the current light/dark mode)."""
        palette, mode = theme.parse_theme(self.theme)
        labels = [theme.PALETTE_LABELS[p] for p in theme.PALETTES]
        idx, _ = await self.ask_choice(
            "Theme palette:", labels, recommended=theme.PALETTES.index(palette)
        )
        if idx is not None:
            chosen = theme.PALETTES[idx]
            self._apply_theme(theme.theme_name(chosen, mode))
            self.notify(f"theme: {chosen} · {mode}")

    async def _model_picker_flow(self) -> None:
        """`/model` — open the full-screen model page (grouped, connected-first) and
        a thinking-level chooser. Updates the active model + footer on confirm."""
        deps = agent.chat_deployments()
        if not deps:
            self.notify("no selectable models in the registry")
            return
        result = await self.push_screen_wait(
            ModelScreen(deps, current_id=self._model, current_level=self._thinking)
        )
        if result:
            self._model, self._thinking = result
            self._refresh_model_status()
            think = f" · think:{self._thinking}" if self._thinking else ""
            self.notify(f"model: {self._model}{think}")

    async def _login_flow(self) -> None:
        """`/login` — store a provider API key (global or this project) and make it
        live immediately, so keyless models unlock without a restart."""
        from visvoai.cli import keys

        providers = sorted({d.provider for d in agent.chat_deployments()})
        if not providers:
            self.notify("no providers in the registry")
            return
        labels = []
        for p in providers:
            src = keys.resolved_source(p, self._cwd)
            labels.append(f"{p}" + (f"  (key set · {src})" if src else "  (no key)"))
        idx, _ = await self.ask_choice("Add an API key for which provider?", labels)
        if idx is None:
            return
        provider = providers[idx]

        key = await self.ask_text(
            f"Paste the {keys.env_var_for(provider)} value:",
            placeholder="stored locally, never committed", multiline=False)
        if not key or not key.strip():
            self.notify("no key entered")
            return

        s_idx, _ = await self.ask_choice(
            "Save where?",
            ["Global — ~/.visvoai (all projects)",
             "This project — .visvoai/secrets.toml (gitignored)"])
        if s_idx is None:
            return
        scope = "global" if s_idx == 0 else "project"
        try:
            keys.set_key(provider, key.strip(), scope, self._cwd)
            keys.load_keys_into_env(self._cwd)   # make it live now
        except OSError as e:
            self.notify(f"could not save key: {e}")
            return
        # If the just-saved provider differs from the active model's provider, the
        # footer stays unchanged and the user reads "models now available" against a
        # still-locked active model — looks like the key didn't take. When the active
        # model lacks a key (the common case — that was why /login ran), switch to
        # the registry's first connected deployment so the change is visible without
        # a manual /model dance. Match the startup logic (app.py:133-134) for the
        # thinking default so the footer reflects the new model.
        if not agent.api_key_available(self._model):
            new_default = agent.default_chat_model()
            if new_default and new_default != self._model:
                self._model = new_default
                _dv = agent.deployment_view(self._model)
                self._thinking = _dv.default_thinking if _dv else None
            self._refresh_model_status()
        else:
            self._refresh_model_status()
        self.notify(f"{provider} key saved ({scope}) — models now available.")

    async def _compact_flow(self) -> None:
        """`/compact` — fold older turns into a summary. Drops a prominent marker
        (states messages folded + window before → after) and resets the gauge."""
        state.record_used("compact")
        before, after = self._ctx_pct, 14
        log = self.query_one("#log", VerticalScroll)
        before_txt = f"{before}%" if before is not None else "—"
        await log.mount(CompactionMarker(
            f"18 messages folded into a summary  ·  {before_txt} → {after}% context"
        ))
        # Keep the token label coherent with the synthetic post-compact % (compact is
        # still a mock fold; derive tokens from the active model's window).
        dv = agent.deployment_view(self._model)
        tokens = round(after / 100 * dv.context_window) if dv and dv.context_window else None
        self._set_context(after, tokens)
        log.scroll_end(animate=False)

    async def on_text_area_changed(self, event) -> None:
        prompt = self.query_one("#prompt", PromptArea)
        if event.text_area is not prompt:
            return
        text = prompt.text
        # Slash command — only at the very start of a single-line input.
        if text.startswith("/") and "\n" not in text:
            await self._hide_file_menu()
            await self._show_slash_menu(text[1:].split(" ")[0])
            prompt.slash_active = True
            return
        # @-mention — an "@frag" at the cursor/end anywhere in the input.
        m = _MENTION_RE.search(text)
        if m is not None:
            await self._hide_slash_menu()
            await self._show_file_menu(m.group(1))
            prompt.slash_active = True   # reuse the nav-key channel; the open menu decides
            return
        await self._hide_slash_menu()
        await self._hide_file_menu()
        prompt.slash_active = False

    async def _show_slash_menu(self, query: str) -> None:
        bottom = self.query_one("#bottom", Vertical)
        menus = bottom.query(SlashMenu)
        if menus:
            menu = menus.first()
        else:
            menu = SlashMenu(SLASH_COMMANDS)
            await bottom.mount(menu, before=self.query_one("#prompt-row", Horizontal))
        await menu.update_query(query)
        self._update_pinned()  # slash menu present → hide the pinned plan

    async def _hide_slash_menu(self) -> None:
        menus = self.query(SlashMenu)
        if menus:
            await menus.remove()
            # Removal alone leaves #bottom at its stale (taller) height, which
            # shifts the prompt up. Force the container to re-measure.
            self.query_one("#bottom", Vertical).refresh(layout=True)
        self._update_pinned()  # slash menu gone → restore the pinned plan

    async def _show_file_menu(self, frag: str) -> None:
        bottom = self.query_one("#bottom", Vertical)
        menus = bottom.query(FileMenu)
        if menus:
            menu = menus.first()
        else:
            menu = FileMenu(gitio.project_files(self._cwd))
            await bottom.mount(menu, before=self.query_one("#prompt-row", Horizontal))
        await menu.update_query(frag)
        self._update_pinned()

    async def _hide_file_menu(self) -> None:
        menus = self.query(FileMenu)
        if menus:
            await menus.remove()
            self.query_one("#bottom", Vertical).refresh(layout=True)
        self._update_pinned()

    async def on_prompt_area_slash_key(self, event: PromptArea.SlashKey) -> None:
        # The nav-key channel is shared; the currently-open menu claims it.
        files = self.query(FileMenu)
        if files:
            await self._handle_file_key(files.first(), event.action)
            return
        menus = self.query(SlashMenu)
        if not menus:
            return
        menu = menus.first()
        if event.action == "up":
            menu.move(-1)
        elif event.action == "down":
            menu.move(1)
        elif event.action == "complete":
            # Tab fills the highlighted command into the prompt (does NOT run it);
            # the Changed handler refilters the menu to the now-exact match.
            name = menu.selected()
            if name:
                prompt = self.query_one("#prompt", PromptArea)
                prompt.text = f"/{name}"
                prompt.move_cursor(prompt.document.end)
        elif event.action == "cancel":
            self.query_one("#prompt", PromptArea).slash_active = False
            await self._hide_slash_menu()
        elif event.action == "accept":
            name = menu.selected()
            prompt = self.query_one("#prompt", PromptArea)
            typed = prompt.text.strip()   # capture before clearing (for did-you-mean)
            prompt.slash_active = False
            prompt.text = ""  # also triggers Changed → menu hides
            await self._hide_slash_menu()
            if name:
                self.run_command(name)
            elif typed.startswith("/"):
                # No command matched what they typed (#4) — suggest the closest.
                self.run_worker(self._suggest_command(typed[1:].split(" ")[0]))

    async def _handle_file_key(self, menu: FileMenu, action: str) -> None:
        prompt = self.query_one("#prompt", PromptArea)
        if action == "up":
            menu.move(-1)
        elif action == "down":
            menu.move(1)
        elif action in ("complete", "accept"):   # tab or enter both insert the path
            path = menu.selected()
            if path:
                self._insert_mention(prompt, path)
            prompt.slash_active = False
            await self._hide_file_menu()
        elif action == "cancel":
            prompt.slash_active = False
            await self._hide_file_menu()

    def _insert_mention(self, prompt: PromptArea, path: str) -> None:
        """Replace the in-progress `@frag` with `@path ` (trailing space ends the
        mention so the menu closes and typing continues fluently)."""
        text = prompt.text
        m = _MENTION_RE.search(text)
        if not m:
            return
        at = text.rfind("@", m.start())   # the '@' that opened this mention
        prompt.text = text[:at] + f"@{path} "
        prompt.move_cursor(prompt.document.end)
        state.record_used("mention")

    def run_command(self, name: str) -> None:
        if name == "theme":
            self.run_worker(self._theme_picker_flow())
        elif name == "clear":
            self.run_worker(self._clear_log())
        elif name == "help":
            self.run_worker(self._show_help())
        elif name == "tour":
            self.run_worker(self._tour_flow())
        elif name == "demo":
            self.run_worker(self._demo_picker())
        elif name == "model":
            self.run_worker(self._model_picker_flow())
        elif name == "login":
            self.run_worker(self._login_flow())
        elif name == "resume":
            self.run_worker(self._open_sessions())
        elif name == "rewind":
            self.action_open_rewind()   # spawns its own worker
        elif name == "branch":
            self.action_open_branches()  # spawns its own worker
        elif name == "fork":
            self.action_open_fork()      # spawns its own worker
        elif name == "export":
            self.action_open_export()    # spawns its own worker
        elif name == "log":
            self.run_worker(self._log_flow())
        elif name == "compact":
            self.run_worker(self._compact_flow())
        elif name == "mode":
            self.action_cycle_hitl_mode()
        elif name == "commit":
            self.run_worker(self._open_git())
        elif name == "choice":
            self.action_permission()  # spawns its own worker
        elif name == "form":
            self.action_form_demo()   # spawns its own worker
        elif name == "error":
            self.run_worker(self.action_error_demo())
        elif name == "output":
            self.run_worker(self.action_output_demo())
        elif name == "quit":
            self.exit()

    async def _clear_log(self) -> None:
        # /clear starts a FRESH conversation — reset the thread + all per-conversation
        # state, not just the visual log. Without this the footer keeps the prior
        # conversation's context gauge + cost, and the next turn silently continues
        # the old thread under the old conversation id.
        self._history = []
        self._conv_id = None
        self._project_id = None
        self._persisted_count = 0
        # Reset the checkpoint chain too — a fresh conversation must re-baseline, not
        # chain onto the cleared conversation's tip.
        self._checkpoints = None
        self._cp_branch = "main"
        self._cp_tip_id = None
        self._cp_tip_sha = None
        self._title_generated = False
        self._conv_cost = 0.0
        self._set_context(None)          # hide the gauge (+ drops the ≥85% nudge)
        self._update_cost_status()       # cost back to 0 → cleared from the footer
        self.set_tab_title(None)         # brand-only until the new thread is titled
        self._turns = 0
        self._last_kind = None
        await self._unpin_plan()
        log = self.query_one("#log", VerticalScroll)
        await log.remove_children()
        # /clear always shows the 'empty / fresh start' copy — the user already
        # knows visvoai (they reached /clear), so the heavy onboarding would be
        # patronising and the 'history' copy is wrong (we just emptied it).
        await log.mount(WelcomeBanner(self._welcome_left, self._welcome_empty))
        self._rotate_placeholder()   # fresh example for the new conversation (#5)

    async def action_request_clear(self) -> None:
        if self._clearing:
            self._cancel_clear_timer()
            self._clearing = False
            self._set_status(None)
            await self._clear_log()
            return
        self._clearing = True
        self._set_status("press Ctrl+K again to clear the conversation")
        self._clear_timer = self.set_timer(2.0, self._revert_clear)

    def _cancel_clear_timer(self) -> None:
        timer = getattr(self, "_clear_timer", None)
        if timer is not None:
            timer.stop()
            self._clear_timer = None

    def _revert_clear(self) -> None:
        self._clear_timer = None
        if self._clearing:
            self._clearing = False
            self._set_status(None)

    def _help_markup(self) -> str:
        primary, secondary, muted = self._tv("primary"), self._tv("secondary"), self._tv("muted")
        desc = dict(SLASH_COMMANDS)
        out = [f"[b {primary}]visvoai — help[/]",
               f"[{muted}]Type to chat. I read & edit files and run commands; you approve "
               f"anything that touches your code.[/]", ""]

        for heading, names in _HELP_GROUPS:
            out.append(f"[b {secondary}]{heading}[/]")
            for n in names:
                out.append(f"  [b {primary}]/{n}[/]  [dim {muted}]{desc.get(n, '')}[/]")
            out.append("")

        out.append(f"[b {secondary}]Keyboard[/]")
        for key, what in _HELP_KEYS:
            out.append(f"  [b {primary}]{key:<11}[/] [dim {muted}]{what}[/]")
        out.append("")

        out.append(f"[b {secondary}]Time travel — how it works[/]")
        out += [
            f"  [{muted}]Every turn auto-saves a [b]checkpoint[/b]: a snapshot of your files "
            f"plus the chat at that point — in a private store, your own git is untouched.[/]",
            f"  [b {primary}]/rewind[/] [dim {muted}]undoes — restores your files AND chat to a "
            f"checkpoint (changes after it are discarded).[/]",
            f"  [b {primary}]/branch[/] [dim {muted}]forks a checkpoint into a second timeline "
            f"and keeps BOTH — switch between them anytime, nothing is lost.[/]",
            f"  [b {primary}]/fork[/]   [dim {muted}]opens a checkpoint in a NEW folder so you can "
            f"try a different approach in parallel.[/]",
            f"  [b {primary}]/export[/] [dim {muted}]saves the chat (and optionally the code) as a "
            f"shareable file.[/]",
        ]
        return "\n".join(out)

    # ── guided tour (#6) ──────────────────────────────────────────────────────
    _TOUR_STEPS: list[tuple[str, str]] = [
        ("Welcome to visvoai",
         "I'm a coding agent in your terminal. Describe a task and I'll read & edit "
         "files and run commands — you approve anything that touches your code."),
        ("Time travel",
         "Every turn auto-saves a checkpoint (your files + the chat) in a private "
         "store — your own git is never touched. Ctrl+B (or /rewind) restores any "
         "earlier point."),
        ("Branch — don't lose work",
         "When you go back, choose 'branch from here' to keep BOTH timelines. /branch "
         "switches between them; /fork opens one in a separate folder to explore in "
         "parallel."),
        ("Approvals",
         "By default I ask before editing files or running shell. Shift+Tab cycles "
         "modes: normal → auto-edit (writes through, shell still asks) → accept-all."),
        ("You're set",
         "/help lists everything, and tips rotate under the spinner while you wait. "
         "So — what would you like to build?"),
    ]

    async def _tour_flow(self) -> None:
        """`/tour` — a paged, opt-in walkthrough of the core features."""
        n = len(self._TOUR_STEPS)
        for i, (title, body) in enumerate(self._TOUR_STEPS):
            last = i == n - 1
            options = ["Done ✓"] if last else ["Next →", "Skip tour"]
            idx, _ = await self.ask_choice(f"[{i + 1}/{n}]  {title}\n\n{body}", options)
            if idx is None or (not last and idx != 0):   # esc or "Skip tour"
                break
        state.record_used("tour")

    async def _suggest_command(self, fragment: str) -> None:
        """`/xyz` matched no command — mount a quiet 'did you mean' hint (#4)."""
        from visvoai.cli.widgets import SystemNote
        guess = _closest_command(fragment)
        if guess:
            msg = f"no /{fragment} — did you mean [b]/{guess}[/]?  ({dict(SLASH_COMMANDS)[guess]})"
        else:
            msg = f"no command /{fragment} — type / to see all, or /help"
        log = self.query_one("#log", VerticalScroll)
        await log.mount(SystemNote(msg, kind="info"))
        log.scroll_end(animate=False)

    async def _show_help(self) -> None:
        state.record_used("help")
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Welcome(self._help_markup))
        log.scroll_end(animate=False)
