"""AgentRunsScreen — watch subagent dispatches live, switch between their logs.

Top: one row per run_agent dispatch (running first). Bottom: the SELECTED run's
step log, tailing live while it runs (1s tick — the registry is fed by the turn
worker on the same loop). Same chrome family as /ps: full-screen, ↑/↓ to switch,
esc to close. Finished runs stay reviewable; the durable full transcript is the
JSONL trace under the conversation's agents/ directory.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.agent_runs import AgentRun, AgentRunRegistry
from visvoai.cli.widgets.run_steps import RunStepsView
from visvoai.cli.iconography import STATE_STYLE
from visvoai.cli.screens.base import BlendScreen
from visvoai.cli.screens.chrome import CHROME_CSS, hint

_STATE = {"running": "running", "done": "ok", "failed": "failed",
          "stopped": "disabled"}


def _dur(seconds: float) -> str:
    s = int(seconds)
    return f"{s}s" if s < 60 else f"{s // 60}m {s % 60:02d}s"


class RunRow(Vertical):
    """One dispatch, two lines: state + agent + runtime, then the task excerpt."""

    can_focus = False

    DEFAULT_CSS = """
    RunRow { height: auto; padding: 0 1; }
    RunRow:hover { background: $hover; }
    RunRow.active { background: $hover; }
    RunRow > .rr-head { height: 1; text-overflow: ellipsis; }
    RunRow > .rr-task { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, run: AgentRun) -> None:
        super().__init__()
        self.index = index
        self.run = run
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="rr-head")
        yield Static(classes="rr-task")

    def on_mount(self) -> None:
        self.render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.render_row()

    def render_row(self) -> None:
        tv = theme.palette(self)
        r = self.run
        icon, token = STATE_STYLE[_STATE[r.status]]
        state_style = f"dim {tv['muted']}" if token == "muted" else tv[token]

        head = Text()
        head.append(" ❯ " if self._active else "   ",
                    style=tv["primary"] if self._active else "dim")
        head.append(f"{icon} ", style=state_style)
        head.append(r.agent, style=f"bold {tv['primary']}" if self._active
                    else f"bold {tv['foreground']}")
        if r.status == "running":
            head.append(f"   running · {_dur(r.duration_s)} · "
                        f"{len(r.steps)} step{'s' if len(r.steps) != 1 else ''}",
                        style=tv["success"])
        else:
            head.append(f"   {r.status} · {_dur(r.duration_s)}", style=state_style)
            if r.summary:
                head.append(f" · {r.summary.strip('[]')}", style=f"dim {tv['muted']}")
        self.query_one(".rr-head", Static).update(head)
        self.query_one(".rr-task", Static).update(
            Text(r.task[:160], style=f"dim {tv['muted']}"))

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class AgentRunsScreen(BlendScreen):
    """Full-screen live view of subagent dispatches. `dismiss(None)` on close."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    AgentRunsScreen { align: center top; }
    /* Full-width (unlike the centered 120-col chrome default): the log pane
       deserves the whole terminal. Run list left (30%), selected log right. */
    #runs-box { max-width: 100%; }
    #runs-split { height: 1fr; }
    #runs-list { width: 30%; height: 100%; }
    #runs-log-wrap { width: 1fr; height: 100%;
                     border-left: solid $foreground 20%; padding: 0 0 0 1; }
    """

    def __init__(self, registry: AgentRunRegistry) -> None:
        super().__init__()
        self.registry = registry
        self.idx = 0

    def _summary(self) -> str:
        runs = self.registry.runs()
        running = sum(1 for r in runs if r.status == "running")
        parts = []
        if running:
            parts.append(f"{running} running")
        if len(runs) - running:
            parts.append(f"{len(runs) - running} finished")
        return " · ".join(parts) or "none yet"

    def compose(self) -> ComposeResult:
        with Vertical(id="runs-box", classes="sc-box"):
            yield Static("Agent runs — live logs of delegated work",
                         id="runs-title", classes="sc-title")
            yield Static(self._summary(), id="runs-sub", classes="sc-sub")
            with Horizontal(id="runs-split"):
                with VerticalScroll(id="runs-list", classes="sc-list"):
                    runs = self.registry.runs()
                    if runs:
                        for i, r in enumerate(runs):
                            yield RunRow(i, r)
                    else:
                        yield Static(
                            "No agent runs yet. When the AI delegates work "
                            "(run_agent), each dispatch shows up here with a live "
                            "step log — full transcripts persist under the "
                            "conversation's agents/ directory.",
                            id="runs-empty", classes="sc-empty")
                with VerticalScroll(id="runs-log-wrap"):
                    yield RunStepsView(show_final=True)
            yield Static(hint(("↑/↓", "switch run"), ("enter", "stop a running agent"),
                              ("esc", "close")),
                         id="runs-hint", classes="sc-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()
        self.set_interval(1.0, self._tick)

    def _rows(self) -> list[RunRow]:
        return list(self.query(RunRow))

    def _tick(self) -> None:
        # New dispatches can appear while the screen is open (parallel fan-out).
        if len(self.registry.runs()) != len(self._rows()):
            self.run_worker(self._rebuild())
            return
        for row in self._rows():
            row.render_row()
        self.query_one("#runs-sub", Static).update(self._summary())
        log = self.query_one(RunStepsView)
        log.sync()
        if log.run is not None and log.run.status == "running":
            self.query_one("#runs-log-wrap", VerticalScroll).scroll_end(animate=False)

    def _sync(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_active(i == self.idx)
        log = self.query_one(RunStepsView)
        if rows and 0 <= self.idx < len(rows):
            rows[self.idx].scroll_visible(animate=False)
            log.show(rows[self.idx].run)
        else:
            log.show(None)

    async def _rebuild(self) -> None:
        box = self.query_one("#runs-list", VerticalScroll)
        await box.remove_children()
        runs = self.registry.runs()
        for i, r in enumerate(runs):
            await box.mount(RunRow(i, r))
        self.idx = min(self.idx, max(len(runs) - 1, 0))
        self._sync()

    def on_key(self, event) -> None:
        rows = self._rows()
        if event.key == "up" and rows:
            self.idx = (self.idx - 1) % len(rows); self._sync(); event.stop()
        elif event.key == "down" and rows:
            self.idx = (self.idx + 1) % len(rows); self._sync(); event.stop()
        elif event.key == "enter" and rows:
            self._stop_selected(); event.stop()

    def _stop_selected(self) -> None:
        """Stop ONE running agent — the dispatch task is cancelled, the caller
        gets 'stopped by user', and the main turn survives."""
        rows = self._rows()
        if not (0 <= self.idx < len(rows)):
            return
        run = rows[self.idx].run
        if run.status == "running" and self.registry.stop(run.dispatch_id):
            self.notify(f"Stopping agent '{run.agent}' — the main agent is told "
                        "you stopped it.", severity="warning")

    def on_run_row_chosen(self, msg: RunRow.Chosen) -> None:
        self.idx = msg.index
        self._sync()

    def action_close(self) -> None:
        self.dismiss(None)
