"""ModelScreen — the full-screen model page.

Two phases in one screen:
  1. Pick a model — grouped by provider, **connected providers first**, locked
     (needs-a-key) ones shown after but not selectable. Full width: name left,
     thinking + per-MTok cost right.
  2. Pick a thinking level — the chosen model's possible levels as chips, its
     default preselected. Skipped for models that expose only one level.

`dismiss((deployment_id, level))` on confirm, or `dismiss(None)` on cancel.
Driven a DeployView list from `agent.chat_deployments()` so the screen stays off
direct visvoai.ai imports.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.screens.base import BlendScreen

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
        return f"{n / 1_000_000:g}M ctx"
    if n >= 1_000:
        return f"{n // 1000}K ctx"
    return f"{n} ctx"


class ModelRow(Horizontal):
    """One model: `dot name … think  $in/$out`. Always selectable; locked (no-key)
    rows render dimmed so the separation reads, but you can still switch to one
    (the turn surfaces the missing key)."""

    DEFAULT_CSS = """
    ModelRow { height: 1; padding: 0 1; }
    ModelRow:hover { background: $hover; }
    ModelRow.current { background: $hover; }
    ModelRow > .mr-name { width: 1fr; text-overflow: ellipsis; }
    ModelRow > .mr-ctx { width: 10; content-align: right middle; }
    ModelRow > .mr-think { width: 8; content-align: right middle; }
    ModelRow > .mr-cost { width: 18; content-align: right middle; }
    """

    class Selected(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, dep, index: int) -> None:
        super().__init__()
        self.dep = dep
        self.index = index   # -1 = locked / not selectable

    def on_click(self) -> None:
        if self.index >= 0:
            self.post_message(self.Selected(self.index))

    def compose(self) -> ComposeResult:
        yield Static(classes="mr-name")
        yield Static(classes="mr-ctx")
        yield Static(classes="mr-think")
        yield Static(classes="mr-cost")

    def on_mount(self) -> None:
        tv = theme.palette(self)
        d = self.dep
        locked = not d.connected
        name = Text()
        name.append("● " if not locked else "○ ", style=tv["primary"] if not locked else f"dim {tv['muted']}")
        name.append(d.display_name, style=tv["foreground"] if not locked else f"dim {tv['muted']}")
        self.query_one(".mr-name", Static).update(name)
        self.query_one(".mr-ctx", Static).update(Text(_fmt_ctx(d.context_window), style=f"dim {tv['muted']}"))
        think = "think" if d.selectable_thinking else ""
        self.query_one(".mr-think", Static).update(Text(think, style=f"dim {tv['muted']}"))
        cost = f"${d.in_cost:g}/${d.out_cost:g}" if not locked else "needs key"
        self.query_one(".mr-cost", Static).update(Text(cost, style=f"dim {tv['muted']}"))


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
    ]

    DEFAULT_CSS = """
    ModelScreen { align: center top; }
    ModelScreen > #model-box { width: 100%; max-width: 96; padding: 1 3; height: 1fr; }

    #model-title { text-style: bold; color: $primary; padding: 0 1; }
    #model-hint { color: $muted; padding: 0 1; margin: 0 0 1 0; }
    #model-list { height: 1fr; }
    .model-section { text-style: bold; padding: 0 1; margin: 1 0 0 0; border-bottom: solid $primary-darken-2; }
    .model-section-connected { color: $success; }
    .model-section-locked { color: $warning; }
    .model-provider { color: $muted; padding: 0 1; margin: 1 0 0 0; }

    #think-panel { height: auto; display: none; padding: 1 1 0 1; border-top: solid $primary-darken-2; margin: 1 0 0 0; }
    #think-panel.shown { display: block; }
    #think-label { color: $primary; text-style: bold; }
    #think-chips { height: 1; margin: 1 0 0 0; }
    """

    def __init__(self, deployments: list, current_id: str = "", current_level=None) -> None:
        super().__init__()
        self.deps = deployments
        self._current_id = current_id
        self._current_level = current_level
        self._phase = "model"            # "model" | "think"
        self._selectable: list = []      # DeployView per selectable row, by index
        self._idx = 0
        self._picked = None              # DeployView chosen in phase 1
        self._think_levels: list[str] = []
        self._think_idx = 0

    # ── phase 1: model list ───────────────────────────────────────────────────
    def _list_widgets(self) -> list:
        connected = sorted([d for d in self.deps if d.connected], key=lambda d: (d.provider, d.display_name))
        locked = sorted([d for d in self.deps if not d.connected], key=lambda d: (d.provider, d.display_name))
        self._selectable = []
        widgets: list = []

        def _provider_groups(deps):
            last_provider = None
            for d in deps:
                if d.provider != last_provider:
                    widgets.append(Static(_provider_label(d.provider), classes="model-provider"))
                    last_provider = d.provider
                idx = len(self._selectable)
                self._selectable.append(d)
                widgets.append(ModelRow(d, index=idx))

        if connected:
            widgets.append(Static("Connected", classes="model-section model-section-connected"))
            _provider_groups(connected)
        if locked:
            widgets.append(Static("Needs an API key", classes="model-section model-section-locked"))
            _provider_groups(locked)
        return widgets

    def compose(self) -> ComposeResult:
        with Vertical(id="model-box"):
            yield Static("Select model", id="model-title")
            yield Static("↑/↓ choose  ·  enter select  ·  esc cancel", id="model-hint")
            with VerticalScroll(id="model-list"):
                yield from self._list_widgets()
            with Vertical(id="think-panel"):
                yield Static("", id="think-label")
                yield Horizontal(id="think-chips")

    def on_mount(self) -> None:
        super().on_mount()
        # Start on the current model if it's selectable, else the first.
        for i, d in enumerate(self._selectable):
            if d.id == self._current_id:
                self._idx = i
                break
        self._sync_rows()

    def _rows(self) -> list:
        return [r for r in self.query(ModelRow) if r.index >= 0]

    def _sync_rows(self) -> None:
        for r in self.query(ModelRow):
            r.set_class(r.index == self._idx, "current")

    def action_prev(self) -> None:
        if self._phase != "model" or not self._selectable:
            return
        self._idx = (self._idx - 1) % len(self._selectable)
        self._sync_rows()

    def action_next(self) -> None:
        if self._phase != "model" or not self._selectable:
            return
        self._idx = (self._idx + 1) % len(self._selectable)
        self._sync_rows()

    async def on_model_row_selected(self, msg: ModelRow.Selected) -> None:
        msg.stop()
        self._idx = msg.index
        self._sync_rows()
        await self._activate()

    # ── phase 2: thinking ─────────────────────────────────────────────────────
    async def _activate(self) -> None:
        """Enter on a model: go to the thinking chooser, or dismiss if there's no
        real choice (single level)."""
        if not self._selectable:
            return
        d = self._selectable[self._idx]
        if not d.selectable_thinking:
            self.dismiss((d.id, d.default_thinking))
            return
        self._picked = d
        self._phase = "think"
        self._think_levels = list(d.thinking_levels)
        start = self._current_level if (self._current_id == d.id and self._current_level in d.thinking_levels) else d.default_thinking
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
            await self._activate()
        else:
            self.dismiss((self._picked.id, self._think_levels[self._think_idx]))

    def action_back(self) -> None:
        if self._phase == "think":
            self._phase = "model"
            self.query_one("#think-panel", Vertical).set_class(False, "shown")
        else:
            self.dismiss(None)
