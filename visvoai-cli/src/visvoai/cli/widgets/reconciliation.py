"""ReconciliationBlock — what a redirect kept, reverted, and added.

When the user redirects mid-turn, `esc` + a "stopped" `SystemNote` leaves them
guessing what state the work is in. A reconciliation is richer: three explicit
sections — kept (preserved), reverted (undone), added (new) — under an amber
header. Display-only; the agent decides the categories, the widget renders them.

Distinct from `SystemNote` (one dim line): this has structure, color coding, and
enough weight to be noticed.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import grid, theme

# (name, icon, color-key, struck) in render order. Empty sections are omitted.
_SECTIONS = [
    ("kept", "✓", "success", False),
    ("reverted", "✗", "error", True),
    ("added", "+", "success", False),
]


class ReconciliationBlock(Vertical):
    """A structured kept/reverted/added summary after a redirect.

    With all three lists empty, only the header renders (no ValueError — a
    redirect that changed nothing is still worth showing)."""

    DEFAULT_CSS = """
    ReconciliationBlock {
        background: transparent;
        height: auto;
        margin: 0;
        padding-left: 1;          /* grid MARGIN — gutter glyph at col 1 */
    }
    ReconciliationBlock > .recon-header { height: auto; padding: 0; }
    ReconciliationBlock > .recon-section { height: auto; padding-left: 2; }  /* col 3 */
    ReconciliationBlock > .recon-item { height: auto; padding-left: 4; }     /* col 5 */
    """

    def __init__(
        self,
        kept: list[str],
        reverted: list[str],
        added: list[str],
        context: str = "",
    ) -> None:
        super().__init__()
        self.kept = kept
        self.reverted = reverted
        self.added = added
        self.context = context

    def compose(self) -> ComposeResult:
        tv = theme.palette(self)
        t = grid.gutter("⟲", f"bold {tv['warning']}")
        t.append(self.context or "redirected", style=f"bold {tv['warning']}")
        yield Static(t, classes="recon-header")

        data = {"kept": self.kept, "reverted": self.reverted, "added": self.added}
        for name, icon, color_key, struck in _SECTIONS:
            items = data[name]
            if not items:
                continue
            head = Text(f"{icon} {name}", style=f"bold {tv[color_key]}")
            yield Static(head, classes=f"recon-section recon-section-{name}")
            item_style = f"strike {tv['muted']}" if struck else tv["muted"]
            for item in items:
                yield Static(Text(item, style=item_style),
                             classes=f"recon-item recon-item-{name}")
