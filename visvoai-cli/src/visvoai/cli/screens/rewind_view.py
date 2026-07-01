"""RewindScreen — pick a checkpoint to rewind the conversation + code back to.

Lists the active branch's checkpoints newest-first (the current point is excluded —
rewinding to it is a no-op). Each row shows the turn label, what kind of point it is
(turn end / before tools / start), how many files differ from now, and when. ↑/↓
navigate, enter selects, esc cancels. `dismiss()` returns the chosen checkpoint id (or
None). Modeled on SessionsScreen.
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

_KIND_TAG = {"turn": "turn end", "pre_batch": "before tools", "baseline": "start"}


class CheckpointRow(Horizontal):
    """One checkpoint: label (left) + `kind · N files · when` (right)."""

    can_focus = False

    DEFAULT_CSS = """
    CheckpointRow { height: 1; padding: 0 1; }
    CheckpointRow:hover { background: $hover; }
    CheckpointRow.active { background: $hover; }
    CheckpointRow > .cr-label { width: 1fr; text-overflow: ellipsis; }
    CheckpointRow > .cr-kind { width: 16; content-align: right middle; }
    CheckpointRow > .cr-files { width: 12; content-align: right middle; }
    CheckpointRow > .cr-when { width: 12; content-align: right middle; }
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
        yield Static(classes="cr-label")
        yield Static(classes="cr-kind")
        yield Static(classes="cr-files")
        yield Static(classes="cr-when")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def _render_row(self) -> None:
        tv = theme.palette(self)
        e = self.entry
        label = Text()
        label.append(" ❯ " if self._active else "   ",
                     style=tv["primary"] if self._active else "dim")
        label.append(e["label"] or "(no prompt)",
                     style=f"bold {tv['primary']}" if self._active else tv["foreground"])
        self.query_one(".cr-label", Static).update(label)
        self.query_one(".cr-kind", Static).update(
            Text(_KIND_TAG.get(e["kind"], e["kind"]), style=tv["muted"]))
        nf = e.get("files")
        files = "—" if nf is None else ("no changes" if nf == 0 else f"{nf} file{'s' if nf != 1 else ''}")
        self.query_one(".cr-files", Static).update(Text(files, style=f"dim {tv['muted']}"))
        self.query_one(".cr-when", Static).update(Text(e.get("when", ""), style=f"dim {tv['muted']}"))

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class RewindScreen(BlendScreen):
    """Full-screen checkpoint picker. `dismiss(checkpoint_id | None)`."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = """
    RewindScreen { align: center top; }
    RewindScreen > #rewind-box { width: 100%; max-width: 120; padding: 1 4; height: 1fr; }
    #rewind-title { text-style: bold; color: $primary; padding: 0 1; }
    #rewind-sub { color: $muted; padding: 0 1; margin: 0 0 1 0; }
    #rewind-list { height: 1fr; }
    #rewind-hint { color: $muted; padding: 0 1; margin: 1 0 0 0; }
    #rewind-empty { color: $muted; padding: 0 1; }
    """

    def __init__(self, entries: list[dict]) -> None:
        super().__init__()
        self.entries = entries
        self.idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="rewind-box"):
            yield Static("Rewind — go back to an earlier point", id="rewind-title")
            yield Static(
                "Each row is a checkpoint your work was auto-saved at. Pick one — then "
                "choose to rewind in place (discard newer) or branch off (keep both). "
                "“files” = how many changed since now.", id="rewind-sub")
            with VerticalScroll(id="rewind-list"):
                if self.entries:
                    for i, e in enumerate(self.entries):
                        yield CheckpointRow(i, e)
                else:
                    yield Static(
                        "No earlier checkpoints yet. One is saved automatically at the "
                        "end of every turn — come back after you've made some changes.",
                        id="rewind-empty")
            yield Static("↑/↓ navigate   enter select   esc cancel", id="rewind-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[CheckpointRow]:
        return list(self.query(CheckpointRow))

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

    def on_checkpoint_row_chosen(self, msg: CheckpointRow.Chosen) -> None:
        self.idx = msg.index
        self._choose()

    def _choose(self) -> None:
        self.dismiss(self.entries[self.idx]["id"] if self.entries else None)

    def action_close(self) -> None:
        self.dismiss(None)
