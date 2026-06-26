"""Output tier-2 — search / save / jump-to-failure for long tool output.

Tier-1 (`ToolOutput`/`StreamingOutput`) truncates to N lines with a `ShowMore`
expander. Tier-2 lets the user navigate the *full* buffer without hunting:

- `OutputToolbar` — a compact muted row (`🔍 search · 💾 save · ⚡ failures`),
  styled like `ShowMore`, shown only when the host is truncated.
- `SearchRow` / `SearchInput` — an inline search box with live substring
  highlighting, next/prev navigation, and a match counter.
- `Tier2Mixin` — the host-side behavior (open/close search, highlight, save,
  jump). `ToolOutput` and `StreamingOutput` mix it in; each supplies
  `_full_buffer()` and `_expand_full()`.

Flag (search expands the body): opening search mounts the *full* buffer so every
match can be highlighted and scrolled to. For the 2000-line CI log this mounts
2000 `OutputLine` widgets — fine for the mock foundation, but real integration
will want a virtualized body (render only the viewport, highlight in the
renderer). Documented here; revisit at integration.
"""
from __future__ import annotations

import inspect
import os
import tempfile
from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Static

from visvoai.cli import theme

# Substring patterns that mark a "failure" line for jump-to-failure. Plain
# case-sensitive substrings — broad enough to catch pytest/go/git/generic logs.
_ERROR_PATTERNS = [
    "FAILED", "Error", "Traceback", "Exception", "AssertionError",
    "panic:", "FATAL", "fatal:", "error:", "FAIL",
]


def find_first_failure(lines: list[str]) -> int | None:
    """Return the index of the first line matching an error pattern, or None."""
    for i, line in enumerate(lines):
        if any(pat in line for pat in _ERROR_PATTERNS):
            return i
    return None


def _highlight(line: str, query: str, base: str, warn_bg: str, fg: str) -> Text:
    """Render `line` with every case-insensitive `query` match bolded on a
    warning background; the rest stays at `base` style."""
    t = Text()
    low, q, n, i = line.lower(), query.lower(), len(query), 0
    while True:
        j = low.find(q, i)
        if j == -1:
            t.append(line[i:], style=base)
            return t
        if j > i:
            t.append(line[i:j], style=base)
        t.append(line[j:j + n], style=f"bold {fg} on {warn_bg}")
        i = j + n


class ToolbarAction(Static):
    """One clickable affordance in the toolbar. Posts `Clicked` with its key."""

    can_focus = False

    DEFAULT_CSS = """
    ToolbarAction { width: auto; height: 1; color: $primary-darken-2; }
    ToolbarAction:hover { color: $primary; background: $hover; }
    """

    class Clicked(Message):
        def __init__(self, action: str) -> None:
            self.action = action
            super().__init__()

    def __init__(self, label: str, action: str) -> None:
        super().__init__(label)
        self.action = action

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.action))


class OutputToolbar(Horizontal):
    """A muted action row hosted below truncated output: search · save · jump.
    Holds the three host callbacks and dispatches clicks to them."""

    can_focus = False

    DEFAULT_CSS = """
    OutputToolbar {
        height: 1; width: 1fr;
        padding: 0 1 0 3;
        background: transparent;
    }
    OutputToolbar .tb-sep { width: auto; height: 1; color: $muted; }
    """

    def __init__(self, buffer: list[str], on_search: Callable,
                 on_save: Callable, on_jump: Callable) -> None:
        super().__init__()
        self.buffer = buffer
        self.on_search = on_search
        self.on_save = on_save
        self.on_jump = on_jump

    def compose(self) -> ComposeResult:
        yield ToolbarAction("🔍 search", "search")
        yield Static(" · ", classes="tb-sep")
        yield ToolbarAction("💾 save", "save")
        yield Static(" · ", classes="tb-sep")
        yield ToolbarAction("⚡ failures", "jump")

    async def on_toolbar_action_clicked(self, msg: ToolbarAction.Clicked) -> None:
        msg.stop()
        cb = {"search": self.on_search, "save": self.on_save,
              "jump": self.on_jump}[msg.action]
        res = cb()
        if inspect.isawaitable(res):
            await res


class SearchInput(Input):
    """Single-line search box. Enter → next, Shift+Enter → prev, Esc → close."""

    DEFAULT_CSS = """
    SearchInput {
        width: 1fr; height: 1;
        border: none; padding: 0; background: transparent;
        color: $foreground;
    }
    SearchInput.no-match { color: $error; }
    SearchInput:focus { border: none; padding: 0; }
    """

    class Query(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class Next(Message):
        pass

    class Prev(Message):
        pass

    class Closed(Message):
        pass

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.post_message(self.Query(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.post_message(self.Next())

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            self.post_message(self.Closed())
        elif event.key == "shift+enter":
            event.stop()
            self.post_message(self.Prev())


class SearchRow(Horizontal):
    """The search box + a `N/M matches` counter, mounted above the toolbar."""

    can_focus = False

    DEFAULT_CSS = """
    SearchRow { height: 1; width: 1fr; padding: 0 1 0 3; }
    SearchRow .match-count { width: auto; height: 1; color: $muted; }
    """

    def compose(self) -> ComposeResult:
        yield SearchInput(placeholder="search…")
        yield Static("", classes="match-count")

    def focus_input(self) -> None:
        self.query_one(SearchInput).focus()

    def set_count(self, current: int, total: int) -> None:
        count = self.query_one(".match-count", Static)
        si = self.query_one(SearchInput)
        if total == 0 and si.value:
            count.update("no matches")
            si.add_class("no-match")
        else:
            count.update(f"{current}/{total} matches" if total else "")
            si.remove_class("no-match")


class Tier2Mixin:
    """Search / save / jump behavior for a truncatable output host.

    The host must supply `_full_buffer()` (the complete line buffer) and an async
    `_expand_full()` (mount every buffer line into `self._line_widgets`, in buffer
    order). Search and jump expand first so matches are mountable + scrollable.
    """

    def _init_tier2(self, tier2: bool) -> None:
        self.tier2 = tier2
        self._line_widgets: list = []
        self._toolbar: OutputToolbar | None = None
        self._search_row: SearchRow | None = None
        self._query = ""
        self._match_indices: list[int] = []
        self._current_match = -1
        self._saved_path: str | None = None

    # ── host hooks ──────────────────────────────────────────────────────────
    def _full_buffer(self) -> list[str]:
        raise NotImplementedError

    async def _expand_full(self) -> None:
        raise NotImplementedError

    def _make_toolbar(self) -> OutputToolbar:
        self._toolbar = OutputToolbar(
            self._full_buffer(), self._open_search, self._save_buffer, self._jump_failure
        )
        return self._toolbar

    # ── search ──────────────────────────────────────────────────────────────
    async def _open_search(self) -> None:
        if self._search_row is not None:
            await self._close_search()
            return
        await self._expand_full()
        self._search_row = SearchRow()
        await self.mount(self._search_row, before=self._toolbar)
        self._search_row.focus_input()

    async def _close_search(self) -> None:
        if self._search_row is None:
            return
        await self._search_row.remove()
        self._search_row = None
        self._query = ""
        self._match_indices = []
        self._current_match = -1
        self._apply_highlights()

    def on_search_input_query(self, msg: SearchInput.Query) -> None:
        msg.stop()
        self._query = msg.value
        q = self._query.lower()
        buf = self._full_buffer()
        self._match_indices = [i for i, l in enumerate(buf) if q and q in l.lower()]
        self._current_match = 0 if self._match_indices else -1
        self._apply_highlights()
        self._scroll_current()
        self._update_count()

    def on_search_input_next(self, msg: SearchInput.Next) -> None:
        msg.stop()
        self._step(1)

    def on_search_input_prev(self, msg: SearchInput.Prev) -> None:
        msg.stop()
        self._step(-1)

    async def on_search_input_closed(self, msg: SearchInput.Closed) -> None:
        msg.stop()
        await self._close_search()

    def _step(self, direction: int) -> None:
        if not self._match_indices:
            return
        self._current_match = (self._current_match + direction) % len(self._match_indices)
        self._apply_highlights()
        self._scroll_current()
        self._update_count()

    def _update_count(self) -> None:
        if self._search_row is not None:
            current = self._current_match + 1 if self._current_match >= 0 else 0
            self._search_row.set_count(current, len(self._match_indices))

    def _scroll_current(self) -> None:
        if self._current_match < 0:
            return
        idx = self._match_indices[self._current_match]
        if idx < len(self._line_widgets):
            self._line_widgets[idx].scroll_visible()

    def _apply_highlights(self) -> None:
        buf = self._full_buffer()
        tv = theme.palette(self)
        for idx, w in enumerate(self._line_widgets):
            if idx >= len(buf):
                break
            w.update(self._render_line(buf[idx], idx, tv))

    def _render_line(self, line: str, idx: int, tv: dict) -> Text:
        muted = tv["muted"]
        if not self._query or self._query.lower() not in line.lower():
            return Text(line, style=muted)
        t = _highlight(line, self._query, muted, tv["warning"], tv["foreground"])
        if (self._match_indices and self._current_match >= 0
                and self._match_indices[self._current_match] == idx):
            return Text("▸ ", style=tv["primary"]) + t
        return t

    # ── save ────────────────────────────────────────────────────────────────
    def _save_buffer(self) -> str:
        fd, path = tempfile.mkstemp(prefix="visvoai-output-", suffix=".log")
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(self._full_buffer()))
        self._saved_path = path
        return path

    # ── jump-to-failure ───────────────────────────────────────────────────────
    async def _jump_failure(self) -> None:
        idx = find_first_failure(self._full_buffer())
        if idx is None:
            return
        await self._expand_full()
        if idx < len(self._line_widgets):
            self._line_widgets[idx].scroll_visible()
