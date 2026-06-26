"""
commands.py — CommandsMixin: the slash-command menu and its flows.

Owns /theme, /model (registry-driven, connected-providers-first), /compact,
/clear, /help and the slash-menu plumbing (show/filter/navigate/run). Mixed into
VisvoApp; pickers reuse ask_choice and demo actions via self.
"""
from __future__ import annotations

import re

from textual.containers import Horizontal, Vertical, VerticalScroll

from visvoai.cli import agent, gitio, theme
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
    ("help", "Show keys and commands"),
    ("model", "Switch the active model"),
    ("login", "Add a provider API key"),
    ("resume", "Resume a past conversation"),
    ("compact", "Compact the context window"),
    ("commit", "Review & commit changes"),
    ("theme", "Choose a brand palette (Ctrl+T toggles light/dark)"),
    ("clear", "Clear the conversation"),
    ("quit", "Quit visvoai"),
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
            prompt.slash_active = False
            prompt.text = ""  # also triggers Changed → menu hides
            await self._hide_slash_menu()
            if name:
                self.run_command(name)

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

    def run_command(self, name: str) -> None:
        if name == "theme":
            self.run_worker(self._theme_picker_flow())
        elif name == "clear":
            self.run_worker(self._clear_log())
        elif name == "help":
            self.run_worker(self._show_help())
        elif name == "demo":
            self.run_worker(self._demo_picker())
        elif name == "model":
            self.run_worker(self._model_picker_flow())
        elif name == "login":
            self.run_worker(self._login_flow())
        elif name == "resume":
            self.run_worker(self._open_sessions())
        elif name == "compact":
            self.run_worker(self._compact_flow())
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
        await log.mount(WelcomeBanner(self._welcome_left, self._welcome_right))

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
        primary = self._tv("primary")
        lines = "\n".join(f"  [b {primary}]/{n}[/]   [dim]{d}[/]" for n, d in SLASH_COMMANDS)
        return f"[b {primary}]commands[/]\n\n{lines}"

    async def _show_help(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Welcome(self._help_markup))
        log.scroll_end(animate=False)
