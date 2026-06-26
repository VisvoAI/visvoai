"""MermaidCard — a prominent, clickable diagram card that REPLACES a ```mermaid
fence inline in an answer. The raw mermaid source is stripped from the rendered
text (it reads like copyable code otherwise); this card stands in its place and,
on click, writes a self-contained HTML viewer into the conversation folder and
opens it in the browser (the app handles the Clicked message).

A bordered accent box — deliberately not a muted note — so it reads as a real
'this is a diagram, open it' affordance at a glance."""
from __future__ import annotations

from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme


class MermaidCard(Static):
    """A one-line bordered card carrying a diagram's mermaid source. On click it
    posts `Clicked(source)` for the app to render + open. Brightens on hover."""

    DEFAULT_CSS = """
    MermaidCard {
        width: auto;
        height: auto;
        margin: 1 1 0 3;        /* align the border to the answer content column */
        padding: 0 2;
        border: round $secondary 60%;
        background: transparent;
    }
    MermaidCard:hover { border: round $secondary; background: $hover; }
    """

    class Clicked(Message):
        def __init__(self, source: str) -> None:
            self.source = source
            super().__init__()

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source
        self._hover = False

    def on_enter(self, event) -> None:
        self._hover = True
        self.refresh()

    def on_leave(self, event) -> None:
        if self._hover:
            self._hover = False
            self.refresh()

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.source))

    def render(self) -> Text:
        tv = theme.palette(self)
        t = Text()
        t.append("◆ ", style=tv["secondary"])
        t.append("Diagram", style=f"bold {tv['secondary']}")
        hint_style = tv["foreground"] if self._hover else tv["muted"]
        t.append("  ·  click to view in browser", style=hint_style)
        return t

    def restyle(self) -> None:
        self.refresh()
