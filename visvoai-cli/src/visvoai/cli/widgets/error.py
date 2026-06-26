"""ErrorBlock — clean inline error rendering (tool error or model error).

Never shows a raw traceback. A red left-bar block: a one-line headline, the
message, and an optional dim detail line. The agent surfaces *what* failed and
*why* in human terms; the stack trace stays out of the user's face.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from visvoai.cli import grid, theme

# Headline + icon per error kind. Unknown kinds fall back to a generic label.
_KINDS = {
    "tool": ("⚠", "tool error"),
    "model": ("⚠", "model error"),
    "network": ("⚠", "connection error"),
}


class ErrorBlock(Static):
    """An error notice with a red left bar. `kind` selects the headline."""

    DEFAULT_CSS = """
    ErrorBlock {
        background: transparent;
        color: $foreground;
        padding: 0 1;
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, kind: str, message: str, detail: str | None = None) -> None:
        super().__init__()
        self.kind = kind
        self.message = message
        self.detail = detail

    def render(self) -> Text:
        tv = theme.palette(self)
        icon, label = _KINDS.get(self.kind, ("⚠", "error"))
        t = grid.gutter(icon, f"bold {tv['error']}")
        t.append(f"{label}\n", style=f"bold {tv['error']}")
        t.append(grid.INDENT + self.message, style=tv["foreground"])  # continue at content col
        if self.detail:
            t.append("\n")
            t.append(grid.INDENT + self.detail, style=f"dim {tv['muted']}")
        return t
