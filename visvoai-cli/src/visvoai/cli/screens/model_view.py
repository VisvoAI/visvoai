"""ModelScreen — the full-screen model page.

Two phases in one screen:
  1. Pick a model — a searchable, virtualized list (handles the full ~4000-model
     catalog smoothly). Type to filter by name/provider; connected models first,
     locked (needs-a-key) ones after. Name left, ctx · thinking · per-MTok cost right.
  2. Pick a thinking level — the chosen model's levels as chips, default preselected.
     Skipped for models that expose only one level.

`dismiss((deployment_id, level))` on confirm, or `dismiss(None)` on cancel. Driven by a
DeployView list from `agent.chat_deployments()` so the screen stays off direct
visvoai.ai imports.

Performance: the picker is a single `OptionList` (rows are lightweight Options, rendered
only when visible) — NOT one Widget per model. Searching rebuilds the option set; nothing
is mounted per row, so hundreds/thousands of models stay responsive.
"""
from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from visvoai.cli import theme
from visvoai.cli.screens.base import BlendScreen
from visvoai.cli.screens.chrome import CHROME_CSS, hint

# Provider id → display name (proper casing; the registry uses lowercase ids).
_PROVIDER_DISPLAY = {
    "gemini": "Gemini", "anthropic": "Anthropic", "openai": "OpenAI",
    "openrouter": "OpenRouter", "together": "Together", "groq": "Groq",
}


def _provider_label(provider: str) -> str:
    return _PROVIDER_DISPLAY.get(provider, provider.title())


def _fmt_ctx(n: int) -> str:
    """Context window as a compact, self-describing label. 0 (unknown) → empty."""
    if not n:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"   # 1048576 → "1M"
    if n >= 1_000:
        return f"{n // 1000}K"
    return str(n)


class ThinkChip(Static):
    """One thinking-level chip in the level chooser — clickable to select it."""

    DEFAULT_CSS = """
    ThinkChip { width: auto; height: 1; padding: 0 1; margin: 0 1 0 0; }
    ThinkChip:hover { background: $hover; }
    ThinkChip.active { background: $hover; }
    """

    class Clicked(Message):
        def __init__(self, level: str) -> None:
            self.level = level
            super().__init__()

    def __init__(self, level: str) -> None:
        super().__init__()
        self.level = level
        self._active = False

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.level))

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.refresh()

    def render(self) -> Text:
        tv = theme.palette(self)
        return Text(self.level, style=f"bold {tv['primary']}" if self._active else tv["muted"])


class ModelScreen(BlendScreen):
    """Full-screen model page. `dismiss((id, level) | None)`."""

    BINDINGS = [
        Binding("escape", "back", "Back / cancel", show=False),
        Binding("up", "prev", "Prev", show=False),
        Binding("down", "next", "Next", show=False),
        Binding("left", "think_prev", "Prev level", show=False),
        Binding("right", "think_next", "Next level", show=False),
        Binding("enter", "confirm", "Select", show=False),
        # sort / filter controls — ctrl combos so they don't collide with the search box
        Binding("ctrl+s", "cycle_sort", "Sort", show=False),
        Binding("ctrl+t", "toggle_thinking", "Thinking only", show=False),
        Binding("ctrl+k", "toggle_connected", "Connected only", show=False),
    ]

    _SORTS = ("name", "cost", "context")
    _SORT_KEY = {
        "name": lambda d: d.display_name.lower(),
        "cost": lambda d: (d.in_cost, d.out_cost, d.display_name.lower()),
        "context": lambda d: (-d.context_window, d.display_name.lower()),
    }

    DEFAULT_CSS = CHROME_CSS + """
    ModelScreen { align: center top; }
    #model-search, #model-search:focus {
        border: none; background: transparent; padding: 0 1; margin: 0 0 1 0;
        border-bottom: solid $primary;
    }
    #model-list { height: 1fr; border: none; padding: 0; background: transparent; }
    #model-list:focus { border: none; }
    #model-list > .option-list--option-highlighted { background: $hover; }
    #model-list > .option-list--option-disabled { color: $muted; }
    
    #think-panel { height: auto; display: none; padding: 1 1 0 1; border-top: solid $primary-darken-2; margin: 1 0 0 0; }
    #think-panel.shown { display: block; }
    #think-label { color: $primary; text-style: bold; }
    #think-chips { height: 1; margin: 1 0 0 0; }
    """

    def __init__(self, deployments: list, current_id: str = "", current_level=None) -> None:
        super().__init__()
        self.deps = deployments
        self._by_id = {d.id: d for d in deployments}
        self._current_id = current_id
        self._current_level = current_level
        self._phase = "model"            # "model" | "think"
        self._picked = None              # DeployView chosen in phase 1
        self._think_levels: list[str] = []
        self._think_idx = 0
        self._sort = "name"              # name | cost | context (within each provider group)
        self._thinking_only = False      # filter: only models that expose a thinking choice
        self._connected_only = False     # filter: hide locked (no-key) providers

    # ── phase 1: searchable model list ────────────────────────────────────────
    def _row(self, dep) -> Table:
        """One model row: indented dot+name (left) + aligned ctx / thinking / cost columns.
        Fixed column widths so the meta lines up as a table down the page."""
        tv = theme.palette(self)
        locked = not dep.connected
        fg = tv["foreground"] if not locked else f"dim {tv['muted']}"
        muted = f"dim {tv['muted']}"

        name = Text("  ")  # indent under the provider header
        name.append("● " if not locked else "○ ", style=tv["primary"] if not locked else muted)
        name.append(dep.display_name, style=fg)

        ctx = _fmt_ctx(dep.context_window)
        ctx_t = Text(f"{ctx} ctx" if ctx else "", style=muted)
        think_t = Text("thinking" if dep.selectable_thinking else "", style=muted)
        cost_t = Text(f"${dep.in_cost:g} / ${dep.out_cost:g}" if not locked else "needs key", style=muted)

        g = Table.grid(expand=True, padding=(0, 2, 0, 0))
        g.add_column(ratio=1, overflow="ellipsis", no_wrap=True)  # name
        g.add_column(width=12, justify="right", no_wrap=True)     # context
        g.add_column(width=10, justify="right", no_wrap=True)     # thinking
        g.add_column(width=16, justify="right", no_wrap=True)     # cost
        g.add_row(name, ctx_t, think_t, cost_t)
        return g

    def _header(self, provider: str, connected: bool, first: bool) -> Option:
        """A provider group header (disabled). A leading blank line spaces groups apart;
        locked providers are tagged so the missing-key state reads at the group level."""
        tv = theme.palette(self)
        t = Text() if first else Text("\n")
        t.append(_provider_label(provider), style=f"bold {tv['foreground']}" if connected
                 else f"bold {tv['muted']}")
        if not connected:
            t.append("   · needs key", style=f"dim {tv['warning']}")
        return Option(t, disabled=True)

    def _options(self, query: str = "") -> list[Option]:
        """Filtered options, grouped by provider — connected providers first, then locked."""
        q = query.strip().lower()

        def _match(d) -> bool:
            if self._thinking_only and not d.selectable_thinking:
                return False
            if self._connected_only and not d.connected:
                return False
            return not q or q in d.display_name.lower() or q in _provider_label(d.provider).lower()

        groups: dict[str, list] = {}
        for d in self.deps:
            if _match(d):
                groups.setdefault(d.provider, []).append(d)

        # connected providers first, then alphabetical by display label
        def _connected(p: str) -> bool:
            return any(d.connected for d in groups[p])

        order = sorted(groups, key=lambda p: (not _connected(p), _provider_label(p).lower()))
        sort_key = self._SORT_KEY[self._sort]

        opts: list[Option] = []
        for p in order:
            opts.append(self._header(p, _connected(p), first=not opts))
            for d in sorted(groups[p], key=sort_key):
                opts.append(Option(self._row(d), id=d.id))
        if not opts:
            opts.append(Option(Text("no models match", style=theme.palette(self)["muted"]), disabled=True))
        return opts

    def _rebuild(self, query: str = "") -> None:
        ol = self.query_one("#model-list", OptionList)
        ol.clear_options()
        ol.add_options(self._options(query))
        # highlight the current model if present, else the first selectable row
        target = None
        for i in range(ol.option_count):
            opt = ol.get_option_at_index(i)
            if opt.id == self._current_id:
                target = i
                break
            if target is None and opt.id is not None:
                target = i
        ol.highlighted = target

    def compose(self) -> ComposeResult:
        with Vertical(id="model-box", classes="sc-box"):
            yield Static("Select model", id="model-title", classes="sc-title")
            yield Input(placeholder="search models…", id="model-search")
            yield OptionList(id="model-list")
            with Vertical(id="think-panel"):
                yield Static("", id="think-label")
                yield Horizontal(id="think-chips")
            yield Static(hint(("type", "search"), ("↑/↓", "choose"), ("enter/click", "select"),
                              ("^s", "sort"), ("^t", "thinking-only"), ("^k", "connected-only"),
                              ("esc", "cancel")), id="model-hint", classes="sc-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._rebuild("")
        self.query_one("#model-hint", Static).update(self._hint_text())
        self.query_one("#model-search", Input).focus()

    # search box drives the filter live
    def on_input_changed(self, msg: Input.Changed) -> None:
        if msg.input.id == "model-search" and self._phase == "model":
            self._rebuild(msg.value)

    def on_input_submitted(self, msg: Input.Submitted) -> None:
        if msg.input.id == "model-search" and self._phase == "model":
            msg.stop()
            self.run_worker(self.action_confirm())

    # clicking a row (OptionList fires this for non-disabled options only)
    async def on_option_list_option_selected(self, msg: OptionList.OptionSelected) -> None:
        if self._phase != "model":
            return
        msg.stop()
        dep = self._by_id.get(msg.option.id)
        if dep:
            await self._activate(dep)

    def _highlighted_dep(self):
        """The DeployView for the currently highlighted row, or None."""
        ol = self.query_one("#model-list", OptionList)
        if ol.highlighted is None:
            return None
        return self._by_id.get(ol.get_option_at_index(ol.highlighted).id)

    def action_prev(self) -> None:
        if self._phase == "model":
            self.query_one("#model-list", OptionList).action_cursor_up()

    def action_next(self) -> None:
        if self._phase == "model":
            self.query_one("#model-list", OptionList).action_cursor_down()

    # ── sort / filter ─────────────────────────────────────────────────────────
    def _apply(self) -> None:
        """Re-render the list for the current search + sort + filters, and refresh the hint."""
        self._rebuild(self.query_one("#model-search", Input).value)
        self.query_one("#model-hint", Static).update(self._hint_text())

    def _hint_text(self) -> str:
        t = "thinking-only" if self._thinking_only else "all"
        c = "connected-only" if self._connected_only else "all"
        return (f"⌃s sort: {self._sort}   ⌃t models: {t}   ⌃k providers: {c}"
                f"   ·   type to search   ↑/↓ enter   esc cancel")

    def action_cycle_sort(self) -> None:
        if self._phase != "model":
            return
        self._sort = self._SORTS[(self._SORTS.index(self._sort) + 1) % len(self._SORTS)]
        self._apply()

    def action_toggle_thinking(self) -> None:
        if self._phase != "model":
            return
        self._thinking_only = not self._thinking_only
        self._apply()

    def action_toggle_connected(self) -> None:
        if self._phase != "model":
            return
        self._connected_only = not self._connected_only
        self._apply()

    # ── phase 2: thinking ─────────────────────────────────────────────────────
    async def _activate(self, dep) -> None:
        """Enter on a model: go to the thinking chooser, or dismiss if there's no
        real choice (single level)."""
        if not dep.selectable_thinking:
            self.dismiss((dep.id, dep.default_thinking))
            return
        self._picked = dep
        self._phase = "think"
        self.set_focus(None)             # let left/right/enter bindings drive the chips
        self._think_levels = list(dep.thinking_levels)
        start = (self._current_level if (self._current_id == dep.id and self._current_level in dep.thinking_levels)
                 else dep.default_thinking)
        self._think_idx = self._think_levels.index(start) if start in self._think_levels else 0
        await self._render_think()

    async def _render_think(self) -> None:
        panel = self.query_one("#think-panel", Vertical)
        panel.set_class(True, "shown")
        self.query_one("#think-label", Static).update(
            Text(f"Thinking level — {self._picked.display_name}", style="bold"))
        chips = self.query_one("#think-chips", Horizontal)
        await chips.remove_children()
        await chips.mount_all(ThinkChip(lvl) for lvl in self._think_levels)
        self._sync_chips()

    def _sync_chips(self) -> None:
        for i, chip in enumerate(self.query(ThinkChip)):
            chip.set_active(i == self._think_idx)

    def on_think_chip_clicked(self, msg: ThinkChip.Clicked) -> None:
        """Clicking a level chip selects it and confirms the choice."""
        msg.stop()
        if self._phase != "think" or msg.level not in self._think_levels:
            return
        self._think_idx = self._think_levels.index(msg.level)
        self._sync_chips()
        self.dismiss((self._picked.id, msg.level))

    def action_think_prev(self) -> None:
        if self._phase != "think":
            return
        self._think_idx = (self._think_idx - 1) % len(self._think_levels)
        self._sync_chips()

    def action_think_next(self) -> None:
        if self._phase != "think":
            return
        self._think_idx = (self._think_idx + 1) % len(self._think_levels)
        self._sync_chips()

    # ── confirm / back ────────────────────────────────────────────────────────
    async def action_confirm(self) -> None:
        if self._phase == "model":
            dep = self._highlighted_dep()
            if dep:
                await self._activate(dep)
        else:
            self.dismiss((self._picked.id, self._think_levels[self._think_idx]))

    def action_back(self) -> None:
        if self._phase == "think":
            self._phase = "model"
            self.query_one("#think-panel", Vertical).set_class(False, "shown")
            self.query_one("#model-search", Input).focus()
        else:
            self.dismiss(None)
