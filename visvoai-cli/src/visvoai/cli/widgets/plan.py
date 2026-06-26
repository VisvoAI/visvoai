"""Plan — a live task tracker the agent updates as it works.

A compact checklist that shows the agent's plan and advances through it: pending
steps are muted `○`, the active step spins and is bold, completed steps get a ✓ and
strike through. The header shows a running `done/total`. This is the "what is it
doing right now" surface — claude-code-style task tracking, driven live during a turn.

The plan also MUTATES mid-turn, because real agents revise their plan:
- `insert(i, label)` adds a step the agent only discovered it needed.
- `abandon(i)` drops a step that turned out unnecessary (never done).
- `supersede(i, replacement)` marks a step that was done then undone (a redirect),
  optionally inserting the step that replaced it (the "branch" case).
- a step may declare `depends_on=<j>` to render an ordering hint ("after «step j»")
  while its prerequisite isn't done — a rendering primitive, not a scheduler; the
  agent still drives start/complete in the right order.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import grid, theme


class PlanStep(Static):
    """One plan item. States: pending / active / done / abandoned / superseded.

    abandoned = dropped without doing; superseded = done then undone (redirect).
    Both render struck + muted but carry distinct glyphs + a suffix so a reviewer
    can tell *why* a step is crossed out."""

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    # On the grid like every other gutter block: icon at col 1, label at col 3.
    # (No extra indent — the icon already offsets the label.)
    DEFAULT_CSS = "PlanStep { height: 1; padding: 0 1; }"

    def __init__(self, label: str, depends_on: int | None = None) -> None:
        super().__init__()
        self.label = label
        self.state = "pending"
        self.depends_on = depends_on
        self._frame = 0
        # Filled by the parent Plan via _refresh_deps(): the prerequisite's label
        # and whether it's satisfied (done). Only shown while pending + unsatisfied.
        self._dep_label: str | None = None
        self._dep_satisfied = False

    def render(self) -> Text:
        tv = theme.palette(self)
        if self.state == "done":
            t = grid.gutter("✓", f"bold {tv['success']}")
            t.append(self.label, style=f"strike {tv['muted']}")
        elif self.state == "active":
            frame = self.SPINNER[self._frame % len(self.SPINNER)]
            t = grid.gutter(frame, tv["secondary"])
            t.append(self.label, style=f"bold {tv['foreground']}")
        elif self.state == "abandoned":
            t = grid.gutter("⊘", f"dim {tv['muted']}")
            t.append(self.label, style=f"strike dim {tv['muted']}")
            t.append("   · abandoned", style=f"dim {tv['muted']}")
        elif self.state == "superseded":
            t = grid.gutter("↻", f"dim {tv['muted']}")
            t.append(self.label, style=f"strike dim {tv['muted']}")
            t.append("   · superseded", style=f"dim {tv['muted']}")
        else:  # pending
            t = grid.gutter("○", f"dim {tv['muted']}")
            t.append(self.label, style=tv["muted"])
            if self._dep_label is not None and not self._dep_satisfied:
                t.append(f"   · after “{self._dep_label}”", style=f"dim {tv['muted']}")
        return t


class Plan(Vertical):
    """A live checklist. `start(i)` activates a step (spins), `complete(i)` ticks it.

    Mutators: `insert`, `abandon`, `supersede`. Mounting mutators are async (Textual
    `mount` is async — awaiting avoids ordering races); state-only mutators are sync.
    """

    DEFAULT_CSS = """
    Plan {
        background: transparent;
        height: auto;
        margin: 0;
        padding: 0;
    }
    /* Header is a gutter block: ◑ at col 1, "Plan · n/m" at col 3. */
    Plan > .plan-header { text-style: bold; color: $primary; padding: 0 1; margin: 0; }
    /* Docked above the input (pinned): a top rule, header sits right under it. */
    Plan.pinned { border-top: solid $primary-darken-2; padding: 0; }
    """

    def __init__(self, steps: list[str], deps: dict[int, int] | None = None) -> None:
        super().__init__()
        self.steps = list(steps)
        # Optional ordering hints: {step_index: prerequisite_index}.
        self._deps = dict(deps or {})

    def compose(self) -> ComposeResult:
        yield Static(classes="plan-header")
        for i, label in enumerate(self.steps):
            yield PlanStep(label, depends_on=self._deps.get(i))

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._tick)
        self._refresh_deps()
        self._render_header()

    def _tick(self) -> None:
        for step in self.query(PlanStep):
            if step.state == "active":
                step._frame += 1
                step.refresh()

    def _rows(self) -> list[PlanStep]:
        return list(self.query(PlanStep))

    def _refresh_deps(self) -> None:
        """Resolve each step's prerequisite to a label + satisfied flag, then
        refresh it so the 'after «dep»' hint appears/clears live."""
        rows = self._rows()
        for row in rows:
            if row.depends_on is not None and 0 <= row.depends_on < len(rows):
                dep = rows[row.depends_on]
                row._dep_label = dep.label
                row._dep_satisfied = dep.state == "done"
            else:
                row._dep_label = None
            row.refresh()

    def _render_header(self) -> None:
        rows = self._rows()
        done = sum(1 for s in rows if s.state == "done")
        # Dropped steps (abandoned / superseded) leave the denominator so a fully
        # finished plan still reads n/n rather than stalling below total.
        dropped = sum(1 for s in rows if s.state in ("abandoned", "superseded"))
        total = len(rows) - dropped
        t = grid.gutter("◑")
        t.append(f"Todo · {done}/{total}")
        self.query_one(".plan-header", Static).update(t)

    def start(self, i: int) -> None:
        self._rows()[i].state = "active"
        self._rows()[i].refresh()
        self._render_header()

    def complete(self, i: int) -> None:
        self._rows()[i].state = "done"
        self._rows()[i].refresh()
        self._refresh_deps()  # a completed step can unblock a dependent's hint
        self._render_header()

    async def insert(self, i: int, label: str, depends_on: int | None = None) -> None:
        """Insert a new step at position `i` (a site the agent only just found)."""
        rows = self._rows()
        i = max(0, min(i, len(rows)))
        # Existing prerequisite indices at/after the insertion point shift by one.
        for row in rows:
            if row.depends_on is not None and row.depends_on >= i:
                row.depends_on += 1
        step = PlanStep(label, depends_on=depends_on)
        if i < len(rows):
            await self.mount(step, before=rows[i])
        else:
            await self.mount(step)
        self.steps.insert(i, label)
        self._refresh_deps()
        self._render_header()

    def abandon(self, i: int) -> None:
        """Drop a step that turned out unnecessary (never completed)."""
        self._rows()[i].state = "abandoned"
        self._rows()[i].refresh()
        self._render_header()

    async def supersede(self, i: int, replacement: str | None = None) -> None:
        """Mark step `i` superseded (done then undone by a redirect). When a
        `replacement` label is given, insert it right after — the "branch" case."""
        self._rows()[i].state = "superseded"
        self._rows()[i].refresh()
        if replacement is not None:
            await self.insert(i + 1, replacement)
        self._render_header()

    def restyle(self) -> None:
        self._refresh_deps()
        self._render_header()

    def stop(self) -> None:
        """Stop the spinner interval (e.g. when a turn is interrupted)."""
        if getattr(self, "_timer", None):
            self._timer.stop()
            self._timer = None

    def on_unmount(self) -> None:
        self.stop()
