"""RewindScreen — pick one of YOUR QUESTIONS to rewind the conversation + code back to.

Each row is a turn: the question you asked (top line) with a summary of what that turn
did under it (the tool calls / reply). Selecting a question restores your files and chat
to the moment just before you asked it. ↑/↓ navigate, enter selects, esc cancels.
`dismiss()` returns the chosen checkpoint id (or None). Modeled on SessionsScreen.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.screens.base import BlendScreen
from visvoai.cli.screens.chrome import CHROME_CSS, hint


class TurnRow(Vertical):
    """One question, two lines: `❯ <question>` then a dim `<activity>` with a right-
    aligned `<files> · <when>` — so the turn is recognizable at a glance."""

    can_focus = False

    DEFAULT_CSS = """
    TurnRow { height: auto; padding: 0 1; }
    TurnRow:hover { background: $hover; }
    TurnRow.active { background: $hover; }
    TurnRow > .tr-q { height: 1; text-overflow: ellipsis; }
    TurnRow > .tr-detail { height: 1; padding: 0 0 0 3; }
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
        yield Static(classes="tr-q")
        yield Static(classes="tr-detail")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def _render_row(self) -> None:
        tv = theme.palette(self)
        e = self.entry
        q = Text()
        q.append(" ❯ " if self._active else "   ",
                 style=tv["primary"] if self._active else "dim")
        q.append(e["question"],
                 style=f"bold {tv['primary']}" if self._active else tv["foreground"])
        self.query_one(".tr-q", Static).update(q)

        # detail line: activity (left) + files · when (right), padded to a width
        nf = e.get("files")
        meta = "" if nf is None else (
            "no file changes" if nf == 0 else f"{nf} file{'s' if nf != 1 else ''} changed")
        when = e.get("when", "")
        right = "  ·  ".join(p for p in (meta, when) if p)
        detail = Text(e.get("activity", ""), style=f"dim {tv['muted']}")
        if right:
            detail.append("   —   ", style=f"dim {tv['muted']}")
            detail.append(right, style=f"dim {tv['muted']}")
        self.query_one(".tr-detail", Static).update(detail)

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class RewindScreen(BlendScreen):
    """Full-screen question picker. `dismiss(checkpoint_id | None)`."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    RewindScreen { align: center top; }
    """

    def __init__(self, entries: list[dict]) -> None:
        super().__init__()
        self.entries = entries
        self.idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="rewind-box", classes="sc-box"):
            yield Static("Rewind — jump back to one of your questions", id="rewind-title", classes="sc-title")
            yield Static(
                "Pick a question — you're taken back to the moment just before you "
                "asked it. Nothing is lost yet: the next step asks what to revert "
                "(code, chat, or both) and always offers a branch instead.",
                id="rewind-sub", classes="sc-sub")
            with VerticalScroll(id="rewind-list", classes="sc-list"):
                if self.entries:
                    for i, e in enumerate(self.entries):
                        yield TurnRow(i, e)
                else:
                    yield Static(
                        "No earlier questions yet. Every turn is checkpointed "
                        "automatically — ask anything, and this screen fills in. "
                        "(Files snapshot to a shadow repo; your own git is never touched.)",
                        id="rewind-empty", classes="sc-empty")
            yield Static(hint(("↑/↓", "navigate"),
                              ("enter", "choose action: revert code / chat / both · summarize · branch"),
                              ("esc", "cancel")), id="rewind-hint", classes="sc-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[TurnRow]:
        return list(self.query(TurnRow))

    def _sync(self) -> None:
        for i, row in enumerate(self._rows()):
            row.set_active(i == self.idx)

    def on_key(self, event) -> None:
        if not self.entries:
            return
        if event.key == "up":
            self.idx = (self.idx - 1) % len(self.entries); self._sync(); event.stop()
        elif event.key == "down":
            self.idx = (self.idx + 1) % len(self.entries); self._sync(); event.stop()
        elif event.key == "enter":
            self._choose(); event.stop()

    def on_turn_row_chosen(self, msg: TurnRow.Chosen) -> None:
        self.idx = msg.index
        self._choose()

    def _choose(self) -> None:
        self.dismiss(self.entries[self.idx]["id"] if self.entries else None)

    def action_close(self) -> None:
        self.dismiss(None)
