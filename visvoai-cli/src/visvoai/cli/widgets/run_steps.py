"""RunStepsView — a subagent run's steps rendered with the CONVERSATION's own
tool vocabulary.

An agent run is an agent conversation, so its activity renders exactly like
one: ToolRow nodes on a wire (verb + consequence color, spinner while running,
✓/✗ + duration on the rail), not timestamped log lines. One widget, two
surfaces: the live side panel (tail of the newest steps) and /runs (full).

sync() diffs against the run's step list: existing rows update in place
(status/rail), new steps mount new rows. Cheap enough to call on a 1s tick.
"""
from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.agent_runs import AgentRun, Step
from visvoai.cli.widgets.tool_row import ToolRow


def _rail_for(step: Step) -> str:
    if step.status == "running":
        return ""
    dur = step.duration_s
    d = f"{dur:.1f}s" if dur < 10 else f"{int(dur)}s"
    if step.status == "failed" and step.output:
        return f"{step.output[:40]} · {d}"
    return d


class RunStepsView(Vertical):
    """ToolRow list bound to one AgentRun. `tail` limits to the newest N steps
    (the side panel); None renders all (the /runs log)."""

    DEFAULT_CSS = """
    RunStepsView { height: auto; }
    RunStepsView > .rsv-more { height: 1; }
    RunStepsView > .rsv-final { height: auto; margin: 1 0 0 0; }
    """

    def __init__(self, run: AgentRun | None = None, tail: int | None = None,
                 show_final: bool = False) -> None:
        super().__init__()
        self.run = run
        self.tail = tail
        self.show_final = show_final
        self._rows: dict[str, ToolRow] = {}   # step.key → row

    def show(self, run: AgentRun | None) -> None:
        """Bind to a (different) run; rebuilds on the next sync."""
        if run is not self.run:
            self.run = run
            self._rows.clear()
            self.remove_children()
        self.sync()

    def sync(self) -> None:
        if self.run is None:
            return
        self.run_worker(self._sync(), exclusive=True)

    async def _sync(self) -> None:
        run = self.run
        if run is None:
            return
        steps = list(run.steps)
        visible = steps[-self.tail:] if self.tail else steps
        visible_keys = {s.key for s in visible}
        # Drop rows that scrolled out of the tail window.
        for key in [k for k in self._rows if k not in visible_keys]:
            row = self._rows.pop(key)
            if row.is_mounted:
                await row.remove()
        for i, step in enumerate(visible):
            row = self._rows.get(step.key)
            if row is None:
                row = ToolRow(step.tool, step.target)
                self._rows[step.key] = row
                await self.mount(row)
            row.set_status(step.status if step.status != "complete" else "complete")
            row.set_rail(_rail_for(step))
        self._rewire(visible)
        await self._sync_chrome(steps, visible)

    def _rewire(self, visible: list) -> None:
        n = len(visible)
        for i, step in enumerate(visible):
            row = self._rows.get(step.key)
            if row is None:
                continue
            if n == 1:
                conn = "╶─"
            elif i == 0:
                conn = "┌─"
            elif i == n - 1:
                conn = "└─"
            else:
                conn = "├─"
            row.set_connector(conn)

    async def _sync_chrome(self, steps: list, visible: list) -> None:
        """The '+N earlier steps' marker (tail mode) and the final answer
        (full mode, once finished)."""
        tv = theme.palette(self)
        hidden = len(steps) - len(visible)
        more = self.query(".rsv-more")
        if hidden > 0:
            text = Text(f"… +{hidden} earlier step{'s' if hidden != 1 else ''}",
                        style=f"dim {tv['muted']}")
            if more:
                more.first(Static).update(text)
            else:
                w = Static(text, classes="rsv-more")
                await self.mount(w, before=0)
        elif more:
            await more.first(Static).remove()

        if self.show_final and self.run is not None and self.run.final:
            final = self.query(".rsv-final")
            body = Text(self.run.final[:2000], style=tv["foreground"])
            if final:
                final.first(Static).update(body)
            else:
                await self.mount(Static(body, classes="rsv-final"))

    def restyle(self) -> None:
        for row in self._rows.values():
            row.refresh()
        self.sync()
