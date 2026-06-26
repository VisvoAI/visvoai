"""FileCreation — a creation-aware tool node.

A created file is NOT a diff: there is no "before", so the +/- diff chrome is
wrong for it. This presents a creation as a wired `write «path»` node with a
`N lines` rail (status already complete) over the full file content, collapsed by
default so a batch of scaffolded files reads as a tidy list, each one click away.

A thin preset over `ToolNode` + `ToolOutput` — it owns the "creation, not edit"
framing so the wiring doesn't reinvent it per case.
"""
from __future__ import annotations

from visvoai.cli.widgets.output import ToolOutput
from visvoai.cli.widgets.tool_row import ToolNode


class FileCreation(ToolNode):
    """A complete file-creation node: `write path` row + collapsed full content."""

    def __init__(self, path: str, content: str, max_lines: int = 12) -> None:
        lines = content.splitlines() or [""]
        super().__init__("create", path, rail=f"{len(lines)} lines")
        self.path = path
        self.line_count = len(lines)
        self.row.set_status("complete")   # the file already exists
        self._pending_body = ToolOutput(lines, max_lines=max_lines)

    def on_mount(self) -> None:
        # Attach the content collapsed — one caret-click away, so a batch of
        # creations doesn't bury the conversation in full file bodies.
        self.run_worker(self.set_body(self._pending_body, collapsed=True))
