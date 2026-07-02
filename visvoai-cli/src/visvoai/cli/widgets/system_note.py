"""SystemNote — a muted, single-line inline notice for non-conversational events.

One widget covers every "the system did/observed something" line: a stopped turn,
an auto-compaction marker, a created git branch, an instructions-loaded hint, or a
plain info line. Distinct from `ErrorBlock` (red, a failure) and `Assistant` (the
reply) — this is quiet, dim chrome the eye can skip.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from visvoai.cli import grid, theme
from visvoai.cli.iconography import NOTE_KINDS as _KINDS


class SystemNote(Static):
    """A dim system line: `icon message`. `kind` selects the icon + accent."""

    DEFAULT_CSS = """
    SystemNote {
        background: transparent;
        padding: 0 1;
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, message: str, kind: str = "info") -> None:
        super().__init__()
        self.message = message
        self.kind = kind

    def render(self) -> Text:
        tv = theme.palette(self)
        icon, accent_key = _KINDS.get(self.kind, _KINDS["info"])
        t = grid.gutter(icon, tv[accent_key])
        t.append(self.message, style=f"dim {tv['muted']}")
        return t


class CompactionMarker(Static):
    """A prominent, unmistakable 'context was compacted' divider. Unlike the quiet
    SystemNote, this is meant to be noticed — a centered, accented, ruled band that
    states exactly what happened (messages folded, window before → after)."""

    DEFAULT_CSS = """
    CompactionMarker {
        background: transparent;
        content-align: center middle;
        border-top: solid $secondary;
        border-bottom: solid $secondary;
        padding: 0 1;
        margin: 1 0;
        height: auto;
    }
    """

    def __init__(self, detail: str) -> None:
        super().__init__()
        self.detail = detail

    def render(self) -> Text:
        tv = theme.palette(self)
        return Text(f"✦  context compacted  ·  {self.detail}",
                    style=f"bold {tv['secondary']}", justify="center")
