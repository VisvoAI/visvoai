"""Citation — a quoted reference excerpt with a source marker.

When the agent migrates code by following a changelog or migration guide, the user
should see *the rule it is applying*, verbatim, not just the agent's paraphrase.
This renders a source header (the guide + optional URL) over a quoted excerpt block
so the citation is visible and auditable — distinct from `Assistant` prose and from
a tool failure body (this is the agent citing a source, not an error). Display-only.

Grid-aligned like the other reference blocks: the header glyph sits in the gutter
(source label at col 3); each quoted line is a `│` bar at col 3 with its text at
col 5.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from visvoai.cli import grid, theme


class Citation(Static):
    """`≡ source` over a `│`-quoted excerpt. `render()` reads the palette live, so
    `restyle()` is just a refresh."""

    DEFAULT_CSS = """
    Citation {
        background: transparent;
        padding: 0 1;          /* gutter glyph → col MARGIN; content → col CONTENT */
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, source: str, excerpt: str, url: str | None = None) -> None:
        super().__init__()
        self.source = source
        self.excerpt = excerpt
        self.url = url

    def render(self) -> Text:
        tv = theme.palette(self)
        t = grid.gutter("≡", tv["secondary"])
        t.append(self.source, style=f"bold {tv['foreground']}")
        if self.url:
            t.append(f"   {self.url}", style=f"dim {tv['muted']}")
        for line in self.excerpt.splitlines():
            t.append("\n")
            t.append(grid.INDENT)            # reach col CONTENT (3)
            t.append("│ ", style=f"dim {tv['muted']}")  # bar at col 3, text at col 5
            t.append(line, style=tv["foreground"])
        return t

    def restyle(self) -> None:
        self.refresh()
