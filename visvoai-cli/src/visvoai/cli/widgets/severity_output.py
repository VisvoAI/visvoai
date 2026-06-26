"""SeverityOutput — tool output that distinguishes errors from warnings and folds
a warning flood behind one toggle.

A dependency upgrade (or any noisy suite run) emits hundreds of deprecation
warnings mixed with the real test results. Rendering them flat buries the signal.
This widget classifies each line — error / warning / normal — colours it, and
collapses the warnings into a single `⚠ N warnings — show` control so the errors
and results read clean. Toggle (click the control, or `toggle()`) reveals them
inline, in their original order.

Errors reuse the same `_ERROR_PATTERNS` as jump-to-failure so "what counts as a
failure" is one definition across the output widgets.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.widgets.output import OutputLine
from visvoai.cli.widgets.output_toolbar import _ERROR_PATTERNS

# Warning markers — checked only after errors, so a line that is both reads as the
# more severe error. Broad substrings covering pytest/python/go/generic warnings.
_WARNING_PATTERNS = ["Warning", "Deprecat", "warning:", "WARN", "deprecated"]


def classify(line: str) -> str:
    """Return 'error' | 'warning' | 'normal' for one output line."""
    if any(pat in line for pat in _ERROR_PATTERNS):
        return "error"
    if any(pat in line for pat in _WARNING_PATTERNS):
        return "warning"
    return "normal"


class WarningFold(Static):
    """The toggle line standing in for a folded run of warnings. Click toggles."""

    can_focus = False

    DEFAULT_CSS = """
    WarningFold { color: $warning; height: 1; padding: 0 1 0 3; }
    WarningFold:hover { background: $hover; }
    """

    class Pressed(Message):
        pass

    def __init__(self, count: int, expanded: bool = False) -> None:
        super().__init__()
        self.count = count
        self.expanded = expanded

    def render(self) -> Text:
        warn = theme.palette(self)["warning"]
        verb = "hide" if self.expanded else "show"
        plural = "warning" if self.count == 1 else "warnings"
        return Text(f"  ⚠ {self.count} {plural} — {verb}", style=warn)

    def on_click(self) -> None:
        self.post_message(self.Pressed())


class SeverityOutput(Vertical):
    """Severity-aware output: errors red, warnings folded behind one toggle."""

    DEFAULT_CSS = """
    SeverityOutput {
        background: transparent;
        padding: 0 1 0 3;   /* aligns under the tool header content (grid.CONTENT) */
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, lines: list[str], folded: bool = True) -> None:
        super().__init__()
        self.lines = lines
        self.folded = folded
        self._warn_count = sum(1 for ln in lines if classify(ln) == "warning")

    def compose(self) -> ComposeResult:
        yield from self._build_body()

    def _line_style(self, sev: str) -> str:
        tv = theme.palette(self)
        return {"error": tv["error"], "warning": tv["warning"], "normal": tv["muted"]}[sev]

    def _build_body(self):
        fold_shown = False
        for line in self.lines:
            sev = classify(line)
            if sev == "warning":
                # Emit the fold control once, where the first warning sits.
                if not fold_shown:
                    yield WarningFold(self._warn_count, expanded=not self.folded)
                    fold_shown = True
                if self.folded:
                    continue  # warning hidden while folded
            yield OutputLine(Text(line, style=self._line_style(sev)))

    async def _rebuild(self) -> None:
        await self.remove_children()
        await self.mount_all(list(self._build_body()))
        self.refresh(layout=True)

    async def toggle(self) -> None:
        """Show/hide the folded warnings."""
        self.folded = not self.folded
        await self._rebuild()

    async def on_warning_fold_pressed(self, msg: WarningFold.Pressed) -> None:
        msg.stop()
        await self.toggle()

    def restyle(self) -> None:
        # Colours are baked into each line's Text, so a palette switch needs a
        # rebuild. Schedule it off the message pump (rebuild is async).
        self.call_later(self._rebuild)
