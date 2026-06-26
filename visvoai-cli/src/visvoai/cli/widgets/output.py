"""Long tool output with collapse/expand.

`ToolOutput` shows up to `max_lines` of monospace output and, when longer, a
clickable `ShowMore` affordance that expands the rest. `ShowMore` is the shared
expander — `CleanDiff` reuses it for large diffs.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.widgets.output_toolbar import Tier2Mixin


class ShowMore(Static):
    """A clickable `… show N more` row. Posts `ShowMore.Pressed` on click/enter."""

    # Not focusable: clicking it must not steal focus from the prompt.
    can_focus = False

    DEFAULT_CSS = """
    ShowMore {
        color: $primary-darken-2;
        height: 1;
        padding: 0 1;
    }
    ShowMore:hover { color: $primary; background: $hover; }
    ShowMore:focus { color: $primary; }
    """

    class Pressed(Message):
        pass

    def __init__(self, hidden: int = 0, noun: str = "lines", expanded: bool = False,
                 streaming: bool = False) -> None:
        super().__init__()
        self.hidden = hidden
        self.noun = noun
        self.expanded = expanded  # when True, this is the 'show less' control
        # When True, this is a live-stream indicator ('… stream truncated, N total'):
        # not clickable — expanding mid-stream would fight the live tail.
        self.streaming = streaming

    def render(self) -> Text:
        color = theme.palette(self)["primary-darken-2"]
        if self.streaming:
            return Text(f"  … stream truncated, {self.hidden} total", style=color)
        if self.expanded:
            return Text("  ↑ show less", style=color)
        return Text(f"  … show {self.hidden} more {self.noun}", style=color)

    def set_streaming_total(self, total: int) -> None:
        """Update the live total shown while streaming, without remounting."""
        self.hidden = total
        self.refresh()

    def on_click(self) -> None:
        if self.streaming:
            return  # inert while streaming
        self.post_message(self.Pressed())

    def on_key(self, event) -> None:
        if self.streaming:
            return
        if event.key == "enter":
            self.post_message(self.Pressed())
            event.stop()


class OutputLine(Static):
    """One monospace output line."""

    DEFAULT_CSS = "OutputLine { height: 1; width: 1fr; }"


class ToolOutput(Tier2Mixin, Vertical):
    """Collapsible block of tool stdout. Truncates to `max_lines` until expanded.
    With `tier2=True`, a truncated view hosts an `OutputToolbar` (search/save/
    jump-to-failure) below the visible lines."""

    DEFAULT_CSS = """
    /* Tool body: aligns under the tool header's content (padding-left = grid.CONTENT). */
    ToolOutput {
        background: transparent;
        color: $muted;
        padding: 0 1 0 3;
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, lines: list[str], max_lines: int = 12, tier2: bool = False) -> None:
        super().__init__()
        self.lines = lines
        self.max_lines = max_lines
        self._expanded = False
        self._init_tier2(tier2)

    def _full_buffer(self) -> list[str]:
        return self.lines

    def compose(self) -> ComposeResult:
        yield from self._build_body()

    def _build_body(self):
        self._line_widgets = []
        truncatable = len(self.lines) > self.max_lines
        visible = self.lines if (self._expanded or not truncatable) else self.lines[: self.max_lines]
        muted = theme.palette(self)["muted"]
        for line in visible:
            w = OutputLine(Text(line, style=muted))
            self._line_widgets.append(w)
            yield w
        if truncatable:
            if self.tier2:
                yield self._make_toolbar()
            yield ShowMore(expanded=True) if self._expanded else ShowMore(
                hidden=len(self.lines) - self.max_lines)

    async def _expand_full(self) -> None:
        self._expanded = True
        await self.remove_children()
        await self.mount_all(list(self._build_body()))

    async def on_show_more_pressed(self, msg: ShowMore.Pressed) -> None:
        msg.stop()
        if self._search_row is not None:
            await self._close_search()
        self._expanded = not self._expanded  # toggle expand / collapse
        await self.remove_children()
        await self.mount_all(list(self._build_body()))
        self.refresh(layout=True)  # re-measure so a collapse reclaims space
