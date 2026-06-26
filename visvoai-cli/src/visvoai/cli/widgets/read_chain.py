"""ReadChainGroup — groups a multi-hop read chain into one readable investigation.

A debugging chain (test → fixture → config → service → helper) renders as a labeled
header over the chain's wired read nodes. Dead-end reads (backtracks) stay on the
wire but are marked: a muted `⊘` status + a `dead end` rail, body folded away. The
app decides what's a backtrack (`mark_backtrack(index)`) — this widget is purely the
rendering primitive.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from visvoai.cli import grid
from visvoai.cli.widgets.tool_row import ToolGroup, ToolNode


class ReadChainGroup(ToolGroup):
    """A labeled, wired chain of read nodes. The `◎ label · N reads` header sits
    above the wire; reads are `ToolNode`s joined by the group's ├─/└─ connectors."""

    DEFAULT_CSS = """
    ReadChainGroup { background: transparent; height: auto; margin: 0; padding: 0; }
    /* Header is a gutter block: ◎ at col 1, "label · N reads" at col 3. */
    ReadChainGroup > .chain-header {
        text-style: bold; color: $secondary; padding: 0 1; margin: 0;
    }
    /* The wired reads indent +2 (to SUBITEM) under the chain header. */
    ReadChainGroup > ToolNode { padding: 0 0 0 2; }
    """

    def __init__(self, label: str = "investigation") -> None:
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        yield Static(classes="chain-header")

    def on_mount(self) -> None:
        self._render_header()

    def _render_header(self) -> None:
        # Single-cell geometric glyph (NOT an emoji) so the header content column
        # lands on the grid exactly like the nested reads below it.
        t = grid.gutter("◎")
        t.append(f"{self.label} · {len(self._items)} reads")
        self.query_one(".chain-header", Static).update(t)

    async def add_node(self, node: ToolNode) -> ToolNode:
        """Append a read node to the chain (joins the wire, bumps the count)."""
        await self.add(node)
        self._render_header()
        return node

    def mark_backtrack(self, index: int) -> None:
        """Mark the read at `index` a dead end: muted ⊘ status + `dead end` rail,
        body folded. Permanent — a backtrack led nowhere, so it stays collapsed."""
        if 0 <= index < len(self._items):
            node = self._items[index]
            node.set_status("stopped")
            node.set_rail("dead end")
            if node._body is not None:
                node.set_collapsed(True)

    def nodes(self) -> list[ToolNode]:
        return list(self._items)

    def restyle(self) -> None:
        self._render_header()
