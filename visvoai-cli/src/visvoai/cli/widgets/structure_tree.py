"""StructureTree — a navigable file-layout tree for scaffold/preview rendering.

When the agent proposes a greenfield project structure, prose or a code block
doesn't let the user *review* it. This renders the layout as a real tree —
connector lines, a caret on directories — and lets the user collapse/expand a
directory to focus. A pure preview surface (no diff, no file content); it answers
"what files will exist and how are they organised" before generation runs.

Input is a nested dict: keys are names, a dict value is a directory, any non-dict
value (None) is a file.
    {"app": {"main.py": None, "models": {"order.py": None}}, "pyproject.toml": None}
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme


def _flatten(layout: dict, prefix: str = "", parents: tuple = ()):
    """Yield (connector_prefix, name, is_dir, path, parent_dir_paths) per node,
    depth-first, with box-drawing connectors precomputed."""
    items = list(layout.items())
    for i, (name, child) in enumerate(items):
        last = i == len(items) - 1
        connector = "└─ " if last else "├─ "
        is_dir = isinstance(child, dict)
        # parents holds ancestor dir *paths*; the last is this node's parent.
        path = (parents[-1] + "/" + name) if parents else name
        yield prefix + connector, name, is_dir, path, parents
        if is_dir:
            ext = "   " if last else "│  "
            yield from _flatten(child, prefix + ext, (*parents, path))


class TreeRow(Static):
    """One node. Directories carry a caret and toggle their subtree on click."""

    can_focus = False

    DEFAULT_CSS = """
    TreeRow { height: 1; padding: 0 1; }
    TreeRow.dir:hover { background: $hover; }
    """

    class Toggled(Message):
        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    def __init__(self, prefix: str, node_name: str, is_dir: bool, path: str,
                 parents: tuple) -> None:
        super().__init__()
        self.prefix = prefix
        self.node_name = node_name
        self.is_dir = is_dir
        self.path = path
        self.parents = parents
        self.collapsed = False
        if is_dir:
            self.add_class("dir")

    def render(self) -> Text:
        tv = theme.palette(self)
        t = Text(self.prefix, style=f"dim {tv['muted']}")
        if self.is_dir:
            t.append(f"{'▸' if self.collapsed else '▾'} ", style=tv["secondary"])
            t.append(f"{self.node_name}/", style=f"bold {tv['foreground']}")
        else:
            t.append("  ", style=tv["muted"])
            t.append(self.node_name, style=tv["foreground"])
        return t

    def on_click(self) -> None:
        if self.is_dir:
            self.collapsed = not self.collapsed
            self.refresh()
            self.post_message(self.Toggled(self.path))


class StructureTree(Vertical):
    """A reviewable project-structure tree with collapsible directories."""

    DEFAULT_CSS = """
    StructureTree {
        background: transparent;
        padding: 0 1 0 3;   /* aligns under the answer content column (grid.CONTENT) */
        margin: 0;
        height: auto;
    }
    """

    def __init__(self, layout: dict) -> None:
        super().__init__()
        self._layout = layout  # `layout` is reserved by Textual (CSS layout)
        self._collapsed: set[str] = set()

    def compose(self) -> ComposeResult:
        for prefix, name, is_dir, path, parents in _flatten(self._layout):
            yield TreeRow(prefix, name, is_dir, path, parents)

    def _apply_visibility(self) -> None:
        for row in self.query(TreeRow):
            # Hidden if any ancestor directory is collapsed.
            row.display = not any(p in self._collapsed for p in row.parents)

    def on_tree_row_toggled(self, msg: TreeRow.Toggled) -> None:
        msg.stop()
        if msg.path in self._collapsed:
            self._collapsed.discard(msg.path)
        else:
            self._collapsed.add(msg.path)
        self._apply_visibility()

    def restyle(self) -> None:
        for row in self.query(TreeRow):
            row.refresh()
