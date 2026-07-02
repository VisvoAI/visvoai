"""SlashMenu — `/`-triggered command palette, claude-code style.

Appears above the prompt when the input starts with `/`, filters live as the
user types, and runs the highlighted command on Enter/Tab. The prompt keeps
focus throughout (the menu never grabs it); the app routes navigation keys here
via `PromptArea`'s slash-key messages.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme


class SlashCommand(Static):
    """One command row: `/name   description`, highlighted when active."""

    DEFAULT_CSS = """
    SlashCommand { height: 1; padding: 0 1; }
    SlashCommand.active { background: $hover; }
    """

    def __init__(self, name: str, desc: str) -> None:
        super().__init__()
        self.cmd = name
        self.desc = desc
        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.refresh()

    def render(self) -> Text:
        tv = theme.palette(self)
        t = Text()
        t.append(f"/{self.cmd}", style=f"bold {tv['primary']}" if self._active else tv["foreground"])
        t.append(f"   {self.desc}", style=f"dim {tv['muted']}")
        return t

    def on_click(self) -> None:
        self.post_message(SlashMenu.Clicked(self.cmd))


class SlashMenu(Vertical):
    """Filtered command list. `update_query()` refilters; `move()`/`selected()`
    drive navigation; clicking a row posts `Clicked` (the app runs it, same as
    enter). Mounting/removal is the app's responsibility."""

    class Clicked(Message):
        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    DEFAULT_CSS = """
    SlashMenu {
        background: transparent;
        margin: 0;
        padding: 0;
        height: auto;
        max-height: 10;
    }
    SlashMenu > .slash-empty { color: $muted; padding: 0 1; height: 1; }
    """

    def __init__(self, commands: list[tuple[str, str]]) -> None:
        super().__init__()
        self.commands = commands
        self.filtered: list[tuple[str, str]] = list(commands)
        self.idx = 0

    def compose(self) -> ComposeResult:
        for name, desc in self.filtered:
            yield SlashCommand(name, desc)

    def on_mount(self) -> None:
        self._sync_active()

    async def update_query(self, query: str) -> None:
        q = query.strip().lower()
        self.filtered = [c for c in self.commands if q in c[0].lower()]
        self.idx = 0
        await self.remove_children()
        if self.filtered:
            await self.mount_all(SlashCommand(n, d) for n, d in self.filtered)
            self._sync_active()
        else:
            await self.mount(Static("no matching commands", classes="slash-empty"))

    def _sync_active(self) -> None:
        for i, row in enumerate(self.query(SlashCommand)):
            row.set_active(i == self.idx)

    def move(self, delta: int) -> None:
        if not self.filtered:
            return
        self.idx = (self.idx + delta) % len(self.filtered)
        self._sync_active()

    def selected(self) -> str | None:
        if not self.filtered:
            return None
        return self.filtered[self.idx][0]
