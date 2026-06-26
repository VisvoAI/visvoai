"""Streaming tool output — a `ToolOutput` that grows as lines arrive.

`StreamingOutput` is the long-running-shell body: lines stream in via
`add_line`, the view shows the live tail (most recent `max_lines`), and once the
stream ends `finalize` freezes it into a normal `ToolOutput`-style collapsible
block. Reuses `OutputLine` + `ShowMore` from `output.py`.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical

from visvoai.cli import theme
from visvoai.cli.widgets.output import OutputLine, ShowMore
from visvoai.cli.widgets.output_toolbar import Tier2Mixin


class StreamingOutput(Tier2Mixin, Vertical):
    """Live shell stdout. While streaming, shows the last `max_lines` lines (the
    tail) so the user watches progress; once `finalize`d, behaves exactly like
    `ToolOutput` (head + expand/collapse)."""

    # Not focusable: clicking it must not steal focus from the prompt.
    can_focus = False

    DEFAULT_CSS = """
    /* Mirrors ToolOutput: aligns under the tool header's content. */
    StreamingOutput {
        background: transparent;
        color: $muted;
        padding: 0 1 0 3;
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, max_lines: int = 12, tier2: bool = False) -> None:
        super().__init__()
        self.max_lines = max_lines
        self._buffer: list[str] = []
        self._finalized = False
        self._expanded = False
        self._show_more: ShowMore | None = None
        self._init_tier2(tier2)

    def _full_buffer(self) -> list[str]:
        return self._buffer

    def compose(self) -> ComposeResult:
        # Mounts empty; lines arrive via add_line. compose() also rebuilds the
        # block after finalize/expand toggles (see _rebuild).
        yield from self._build_children()

    def lines(self) -> list[str]:
        """The full accumulated buffer (for tests / later tier-2 features)."""
        return list(self._buffer)

    # ── streaming hot path ────────────────────────────────────────────────
    def add_line(self, line: str) -> None:
        """Append one line and re-render the live tail. Cheap: keeps the tail
        widgets mounted and only `update()`s their text."""
        self._buffer.append(line)
        if self._finalized:
            return  # frozen — no more streaming
        muted = theme.palette(self)["muted"]
        truncatable = len(self._buffer) > self.max_lines
        visible = self._buffer[-self.max_lines:] if truncatable else list(self._buffer)
        # Grow the mounted tail until it reaches max_lines, then it stays put.
        while len(self._line_widgets) < len(visible):
            w = OutputLine("")
            self._line_widgets.append(w)
            self.mount(w)
        for w, text in zip(self._line_widgets, visible):
            w.update(Text(text, style=muted))
        if truncatable:
            if self._show_more is None:
                self._show_more = ShowMore(hidden=len(self._buffer), streaming=True)
                self.mount(self._show_more)
            else:
                self._show_more.set_streaming_total(len(self._buffer))

    def finalize(self) -> None:
        """Mark the stream done and freeze the view as a `ToolOutput`-style block
        (head + a normal expand/collapse `ShowMore`). Idempotent."""
        if self._finalized:
            return
        self._finalized = True
        self._rebuild()

    # ── post-finalize expand/collapse (same contract as ToolOutput) ────────
    async def on_show_more_pressed(self, msg: ShowMore.Pressed) -> None:
        # Only reachable after finalize — streaming ShowMore is inert.
        msg.stop()
        if self._search_row is not None:
            await self._close_search()
        self._expanded = not self._expanded
        await self.remove_children()
        self._line_widgets = []
        self._show_more = None
        await self.mount_all(list(self._build_children()))
        self.refresh(layout=True)

    async def _expand_full(self) -> None:
        # Tier-2 search/jump expand the finalized view so the full buffer mounts.
        self._finalized = True
        self._expanded = True
        await self.remove_children()
        self._line_widgets = []
        self._show_more = None
        await self.mount_all(list(self._build_children()))

    # ── internals ──────────────────────────────────────────────────────────
    def _build_children(self):
        muted = theme.palette(self)["muted"]
        truncatable = len(self._buffer) > self.max_lines
        if self._finalized:
            visible = self._buffer if (self._expanded or not truncatable) else self._buffer[: self.max_lines]
        else:
            visible = self._buffer[-self.max_lines:] if truncatable else list(self._buffer)
        for line in visible:
            w = OutputLine(Text(line, style=muted))
            self._line_widgets.append(w)
            yield w
        if truncatable:
            # Tier-2 toolbar appears only on the frozen (finalized) view — never
            # while streaming, where searching a moving tail is disorienting.
            if self._finalized and self.tier2:
                yield self._make_toolbar()
            if not self._finalized:
                sm = ShowMore(hidden=len(self._buffer), streaming=True)
            elif self._expanded:
                sm = ShowMore(expanded=True)
            else:
                sm = ShowMore(hidden=len(self._buffer) - self.max_lines)
            self._show_more = sm
            yield sm

    def _rebuild(self) -> None:
        """Full remount — used on finalize (and expand toggles go through the
        async handler). Fire-and-forget: Textual serializes the remove then the
        mount, and finalize runs once at end-of-stream."""
        self._line_widgets = []
        self._show_more = None
        self.remove_children()
        self.mount_all(list(self._build_children()))
