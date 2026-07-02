"""BranchScreen — switch between conversation branches, or start a new one.

Branches are divergent timelines (the tree model): each has its own thread + code
tip. The list shows every branch with its latest prompt + when, the active one marked.
A leading "＋ new branch from a checkpoint…" row starts a fork. ↑/↓ navigate, enter
selects, esc cancels. `dismiss()` returns a branch name, the sentinel "+new", or None.
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
from visvoai.cli.screens.chrome import CHROME_CSS, hint

NEW_BRANCH = "+new"


class BranchRow(Horizontal):
    can_focus = False

    DEFAULT_CSS = """
    BranchRow { height: 1; padding: 0 1; }
    BranchRow:hover { background: $hover; }
    BranchRow.active { background: $hover; }
    BranchRow > .br-name { width: 1fr; text-overflow: ellipsis; }
    BranchRow > .br-when { width: 12; content-align: right middle; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, entry: dict) -> None:
        super().__init__()
        self.index = index
        self.entry = entry
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="br-name")
        yield Static(classes="br-when")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def _render_row(self) -> None:
        tv = theme.palette(self)
        e = self.entry
        name = Text()
        name.append(" ❯ " if self._active else "   ",
                    style=tv["primary"] if self._active else "dim")
        if e.get("name") == NEW_BRANCH:
            name.append("＋ new branch from a checkpoint…",
                        style=f"bold {tv['secondary']}" if self._active else tv["secondary"])
        else:
            marker = "● " if e.get("current") else "  "
            name.append(marker, style=tv["primary"] if e.get("current") else "dim")
            name.append(e["name"], style=f"bold {tv['primary']}" if self._active else tv["foreground"])
            if e.get("label"):
                name.append(f"   {e['label']}", style=f"dim {tv['muted']}")
        self.query_one(".br-name", Static).update(name)
        self.query_one(".br-when", Static).update(Text(e.get("when", ""), style=f"dim {tv['muted']}"))

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class BranchScreen(BlendScreen):
    """`dismiss(branch_name | '+new' | None)`."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    BranchScreen { align: center top; }
    BranchScreen > .sc-box { max-width: 110; }
    """

    def __init__(self, entries: list[dict]) -> None:
        super().__init__()
        # entries: branch dicts; a NEW_BRANCH sentinel is prepended here.
        self.entries = [{"name": NEW_BRANCH}] + entries
        self.idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="branch-box", classes="sc-box"):
            yield Static("Branches — your saved timelines", id="branch-title", classes="sc-title")
            yield Static(
                "Each branch is an independent timeline of THIS conversation — its own "
                "chat + files (not a git branch; your repo is untouched). Selecting one "
                "switches to it; ● marks the current one. Nothing is ever lost.",
                id="branch-sub", classes="sc-sub")
            with VerticalScroll(id="branch-list", classes="sc-list"):
                for i, e in enumerate(self.entries):
                    yield BranchRow(i, e)
            yield Static(hint(("↑/↓", "navigate"), ("enter", "switch (or ＋ start a new branch)"),
                              ("esc", "cancel")), id="branch-hint", classes="sc-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[BranchRow]:
        return list(self.query(BranchRow))

    def _sync(self) -> None:
        for i, row in enumerate(self._rows()):
            row.set_active(i == self.idx)

    def on_key(self, event) -> None:
        if event.key == "up":
            self.idx = (self.idx - 1) % len(self.entries); self._sync(); event.stop()
        elif event.key == "down":
            self.idx = (self.idx + 1) % len(self.entries); self._sync(); event.stop()
        elif event.key == "enter":
            self._choose(); event.stop()

    def on_branch_row_chosen(self, msg: BranchRow.Chosen) -> None:
        self.idx = msg.index
        self._choose()

    def _choose(self) -> None:
        self.dismiss(self.entries[self.idx]["name"])

    def action_close(self) -> None:
        self.dismiss(None)
