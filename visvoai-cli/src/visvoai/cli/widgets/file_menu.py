"""FileMenu — `@`-triggered file picker, sibling of SlashMenu.

Appears above the prompt when an `@frag` mention is being typed, filters the
project's files live, and inserts the highlighted path on Enter/Tab. The prompt
keeps focus throughout; the app routes navigation keys here (it reuses the
PromptArea slash-key channel, picking the menu that is currently open).
"""
from __future__ import annotations

import os

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import theme


def rank_files(paths: list[str], frag: str, limit: int = 10) -> list[str]:
    """Substring filter on the path, ranked: basename matches first, then shorter
    paths. Empty frag → the first `limit` files as-is."""
    q = frag.strip().lower()
    if not q:
        return paths[:limit]
    hits = [p for p in paths if q in p.lower()]
    hits.sort(key=lambda p: (q not in os.path.basename(p).lower(), len(p)))
    return hits[:limit]


class FileRow(Static):
    """One file row: dimmed dir + emphasized basename, highlighted when active."""

    DEFAULT_CSS = """
    FileRow { height: 1; padding: 0 1; }
    FileRow.active { background: $hover; }
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.refresh()

    def render(self) -> Text:
        tv = theme.palette(self)
        head, _, tail = self.path.rpartition("/")
        t = Text()
        t.append("@", style=tv["primary"] if self._active else f"dim {tv['muted']}")
        if head:
            t.append(head + "/", style=f"dim {tv['muted']}")
        t.append(tail, style=f"bold {tv['primary']}" if self._active else tv["foreground"])
        return t


class FileMenu(Vertical):
    """Filtered file list over a fixed candidate set. `update_query()` refilters;
    `move()`/`selected()` drive navigation. Mounting/removal is the app's job."""

    DEFAULT_CSS = """
    FileMenu {
        background: transparent;
        margin: 0;
        padding: 0;
        height: auto;
        max-height: 10;
    }
    FileMenu > .file-empty { color: $muted; padding: 0 1; height: 1; }
    """

    def __init__(self, paths: list[str]) -> None:
        super().__init__()
        self.paths = paths
        self.filtered: list[str] = rank_files(paths, "")
        self.idx = 0

    def compose(self) -> ComposeResult:
        for p in self.filtered:
            yield FileRow(p)

    def on_mount(self) -> None:
        self._sync_active()

    async def update_query(self, frag: str) -> None:
        self.filtered = rank_files(self.paths, frag)
        self.idx = 0
        await self.remove_children()
        if self.filtered:
            await self.mount_all(FileRow(p) for p in self.filtered)
            self._sync_active()
        else:
            await self.mount(Static("no matching files", classes="file-empty"))

    def _sync_active(self) -> None:
        for i, row in enumerate(self.query(FileRow)):
            row.set_active(i == self.idx)

    def move(self, delta: int) -> None:
        if not self.filtered:
            return
        self.idx = (self.idx + delta) % len(self.filtered)
        self._sync_active()

    def selected(self) -> str | None:
        if not self.filtered:
            return None
        return self.filtered[self.idx]
