"""ProcessScreen — background processes: what's running, stop it, read its output.

The agent starts servers/watchers via start_process; this is the user's window
into (and kill switch for) those. Same pattern as MCPScreen: full-screen, rows
navigable, actions on enter. `dismiss(None)` — actions apply immediately.
"""
from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.processes import ProcessRegistry, describe_cmd
from visvoai.cli.screens.base import BlendScreen


def _age(started_at: float) -> str:
    s = int(time.time() - started_at)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


class ProcRow(Vertical):
    """One process, two lines: state + command + runtime, then last output line."""

    can_focus = False

    DEFAULT_CSS = """
    ProcRow { height: auto; padding: 0 1; margin: 0 0 1 0; }
    ProcRow:hover { background: $hover; }
    ProcRow.active { background: $hover; }
    ProcRow > .pr-head { height: 1; text-overflow: ellipsis; }
    ProcRow > .pr-tail { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, proc) -> None:
        super().__init__()
        self.index = index
        self.proc = proc
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="pr-head")
        yield Static(classes="pr-tail")

    def on_mount(self) -> None:
        self.render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.render_row()

    def render_row(self) -> None:
        tv = theme.palette(self)
        info = self.proc.info()
        running = info.status == "running"

        head = Text()
        head.append(" ❯ " if self._active else "   ",
                    style=tv["primary"] if self._active else "dim")
        head.append("⏵ " if running else "○ ", style="green" if running else f"dim {tv['muted']}")
        head.append(f"{info.id}  ", style=f"dim {tv['muted']}")
        head.append(describe_cmd(info.command),
                    style=f"bold {tv['primary']}" if self._active else f"bold {tv['foreground']}")
        if running:
            head.append(f"   running · {_age(info.started_at)}", style="green")
        else:
            by = f" by {info.stopped_by}" if info.stopped_by else ""
            head.append(f"   {info.status}{by} (exit {info.returncode})",
                        style=f"dim {tv['muted']}")
        self.query_one(".pr-head", Static).update(head)

        tail = self.proc.tail(1)
        action = "enter: stop" if running else "enter: dismiss"
        t = Text()
        if tail:
            t.append(tail[:100], style=f"dim {tv['muted']}")
            t.append("   ", style=tv["muted"])
        t.append(action, style=f"dim {tv['secondary']}")
        self.query_one(".pr-tail", Static).update(t)

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class ProcessScreen(BlendScreen):
    """Full-screen background-process manager. Actions apply immediately;
    `dismiss(None)` on close."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = """
    ProcessScreen { align: center top; }
    ProcessScreen > #ps-box { width: 100%; max-width: 120; padding: 1 4; height: 1fr; }
    #ps-title { text-style: bold; color: $primary; padding: 0 1; }
    #ps-sub { color: $muted; padding: 0 1; margin: 0 0 1 0; }
    #ps-list { height: 1fr; }
    #ps-hint { color: $muted; padding: 0 1; margin: 1 0 0 0; }
    #ps-empty { color: $muted; padding: 0 1; }
    """

    def __init__(self, registry: ProcessRegistry) -> None:
        super().__init__()
        self.registry = registry
        self.idx = 0

    def _procs(self):
        # running first, then most recent
        procs = [self.registry.get(i.id) for i in self.registry.list()]
        return sorted(procs, key=lambda p: (p.status() != "running", -p.started_at))

    def _summary(self) -> str:
        infos = self.registry.list()
        running = sum(1 for i in infos if i.status == "running")
        done = len(infos) - running
        parts = []
        if running:
            parts.append(f"{running} running")
        if done:
            parts.append(f"{done} finished")
        return " · ".join(parts) or "none"

    def compose(self) -> ComposeResult:
        with Vertical(id="ps-box"):
            yield Static("Background processes", id="ps-title")
            yield Static(
                "Servers and watchers the agent started with start_process. They keep "
                "running between turns; everything here is killed when the app exits.",
                id="ps-sub")
            with VerticalScroll(id="ps-list"):
                procs = self._procs()
                if procs:
                    for i, p in enumerate(procs):
                        yield ProcRow(i, p)
                else:
                    yield Static(
                        "Nothing running. When the agent needs a dev server or watcher "
                        "it starts one here — or ask it to (\"run the app in the "
                        "background\").", id="ps-empty")
            yield Static("↑/↓ navigate   enter stop / dismiss   r refresh   esc close",
                         id="ps-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()
        # Live view: runtimes tick and exits show up while the screen is open.
        self.set_interval(1.0, self._refresh_rows)

    def _rows(self) -> list[ProcRow]:
        return list(self.query(ProcRow))

    def _refresh_rows(self) -> None:
        for row in self._rows():
            row.render_row()
        sub = self.query_one("#ps-sub", Static)
        # summary line stays static text; only rows tick

    def _sync(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_active(i == self.idx)
        if rows and 0 <= self.idx < len(rows):
            rows[self.idx].scroll_visible(animate=False)

    async def _rebuild(self) -> None:
        """Re-compose the list after a stop/dismiss changed the set."""
        box = self.query_one("#ps-list", VerticalScroll)
        await box.remove_children()
        procs = self._procs()
        if procs:
            for i, p in enumerate(procs):
                await box.mount(ProcRow(i, p))
        else:
            await box.mount(Static(
                "Nothing running. When the agent needs a dev server or watcher it "
                "starts one here — or ask it to.", id="ps-empty"))
        self.idx = min(self.idx, max(len(procs) - 1, 0))
        self._sync()

    def on_key(self, event) -> None:
        rows = self._rows()
        if event.key == "up" and rows:
            self.idx = (self.idx - 1) % len(rows); self._sync(); event.stop()
        elif event.key == "down" and rows:
            self.idx = (self.idx + 1) % len(rows); self._sync(); event.stop()
        elif event.key == "enter" and rows:
            self.run_worker(self._act(self.idx)); event.stop()
        elif event.key == "r":
            self.run_worker(self._rebuild()); event.stop()

    def on_proc_row_chosen(self, msg: ProcRow.Chosen) -> None:
        self.idx = msg.index
        self._sync()
        self.run_worker(self._act(msg.index))

    async def _act(self, index: int) -> None:
        rows = self._rows()
        if not (0 <= index < len(rows)):
            return
        proc = rows[index].proc
        if proc.status() == "running":
            import asyncio
            await asyncio.to_thread(proc.stop, "user")
        else:
            self.registry.dismiss(proc.id)
        await self._rebuild()

    def action_close(self) -> None:
        self.dismiss(None)
