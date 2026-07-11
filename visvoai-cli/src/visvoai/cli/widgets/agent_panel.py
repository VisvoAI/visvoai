"""AgentPanel — the live side panel for running subagents.

Splits the main screen while dispatches are active: conversation left (60%),
up to MAX_PANES running agents right (40%). Each pane = a header
(`⏵ name · 1m 42s · 9 steps`) + the tail of its steps rendered by RunStepsView
— the SAME ToolRow vocabulary as the conversation, because an agent run IS an
agent conversation. Appears when agents are running AND the terminal is wide
enough (MIN_APP_WIDTH); collapses when the last one finishes. /runs is the
full-detail view.
"""
from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.agent_runs import AgentRun, AgentRunRegistry
from visvoai.cli.widgets.run_steps import RunStepsView

MAX_PANES = 4        # visible running agents; beyond that a "+N more" line
MIN_APP_WIDTH = 110  # below this the split is cramped — footer pulses only
PANE_TAIL = 6        # step rows per pane


def _dur(seconds: float) -> str:
    s = int(seconds)
    return f"{s}s" if s < 60 else f"{s // 60}m {s % 60:02d}s"


class _RunPane(Vertical):
    """One running agent: header line + the tail of its step rows."""

    can_focus = False

    DEFAULT_CSS = """
    _RunPane { height: auto; margin: 0 0 1 0; }
    /* Soft rule between stacked agents — same 20% keyline family as the split edge. */
    _RunPane.ap-divider { border-top: solid $foreground 20%; padding-top: 1; }
    _RunPane > .ap-head { height: 1; text-overflow: ellipsis; }
    """

    def __init__(self, run: AgentRun, divided: bool = False) -> None:
        super().__init__()
        self.run = run
        if divided:
            self.add_class("ap-divider")

    def compose(self):
        yield Static(classes="ap-head")
        yield RunStepsView(self.run, tail=PANE_TAIL)

    def on_mount(self) -> None:
        self.tick()

    def tick(self) -> None:
        tv = theme.palette(self)
        r = self.run
        head = Text()
        head.append("⏵ ", style=tv["secondary"])
        head.append(r.agent, style=f"bold {tv['foreground']}")
        head.append(f" · {_dur(r.duration_s)} · {len(r.steps)} step"
                    f"{'s' if len(r.steps) != 1 else ''}", style=f"dim {tv['muted']}")
        self.query_one(".ap-head", Static).update(head)
        self.query_one(RunStepsView).sync()

    def restyle(self) -> None:
        self.tick()


class AgentPanel(Vertical):
    """The right-hand split (40%). The APP owns visibility (show/hide from its
    registry poll); the panel owns its content tick while shown."""

    DEFAULT_CSS = """
    AgentPanel { width: 40%; padding: 1 1 0 1;
                 border-left: solid $foreground 20%; display: none; }
    AgentPanel.visible { display: block; }
    AgentPanel > #ap-more { height: auto; }
    """

    def __init__(self, registry: AgentRunRegistry) -> None:
        super().__init__()
        self.registry = registry

    def compose(self):
        yield Static(id="ap-more")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _active_runs(self) -> list[AgentRun]:
        # NOT named `_running` — that's an existing Textual Widget attribute.
        return [r for r in self.registry.runs() if r.status == "running"]

    def _tick(self) -> None:
        if not self.has_class("visible"):
            return
        running = self._active_runs()
        panes = list(self.query(_RunPane))
        want = running[:MAX_PANES]
        if [id(r) for r in want] != [id(p.run) for p in panes]:
            self.run_worker(self._rebuild(want))
        else:
            for p in panes:
                p.tick()
        tv = theme.palette(self)
        more = Text()
        if len(running) > MAX_PANES:
            more = Text(f"+{len(running) - MAX_PANES} more — /runs",
                        style=f"dim {tv['muted']}")
        self.query_one("#ap-more", Static).update(more)

    async def _rebuild(self, want: list[AgentRun]) -> None:
        for p in list(self.query(_RunPane)):
            await p.remove()
        more = self.query_one("#ap-more", Static)
        for i, r in enumerate(want):
            await self.mount(_RunPane(r, divided=i > 0), before=more)

    def restyle(self) -> None:
        self._tick()
        for p in self.query(_RunPane):
            p.restyle()
