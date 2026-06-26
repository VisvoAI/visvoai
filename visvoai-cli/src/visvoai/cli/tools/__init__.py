"""
visvoai.cli.tools — Core developer tool CLI toolkit.

Plain LangChain @tool functions — no datastore, pure local operations — grouped
by concern across submodules; this package is the aggregator that exposes them.

  files.py   read_file · write_file · edit_file · list_files · list_tree
  shell.py   run_shell (30s timeout)
  web.py     web_search (grounded answer) · web_fetch (one URL → markdown)
  _common.py shared output-bounding helpers (cap_lines, clip_line)

Usage:
  from visvoai.cli.tools import build_cli_tools
  tools = build_cli_tools(cwd="/path/to/project")
"""
import inspect
from typing import List, Optional

from langchain_core.tools import BaseTool

from visvoai.cli.tools._common import MAX_LINE_LEN, cap_lines, clip_line
from visvoai.cli.tools.files import (
    LIST_CAP,
    READ_LINE_CAP,
    TREE_DEPTH,
    TREE_PER_DIR_CAP,
    TREE_TOTAL_CAP,
    edit_file,
    list_files,
    list_tree,
    read_file,
    write_file,
)
from visvoai.cli.tools.shell import SHELL_LINE_CAP, run_shell
from visvoai.cli.tools.web import WEB_LINE_CAP, web_fetch, web_search

# The model sees each tool's docstring verbatim as its description; dedent the
# multi-line ones so the schema isn't littered with the source's indentation.
for _t in (read_file, write_file, edit_file, list_files, list_tree, run_shell,
           web_search, web_fetch):
    _t.description = inspect.cleandoc(_t.description)


def build_cli_tools(cwd: Optional[str] = None) -> List[BaseTool]:
    """Return the standard CLI tool set. cwd is reserved for future path-scoping."""
    return [read_file, write_file, edit_file, list_files, list_tree, run_shell,
            web_search, web_fetch]


__all__ = [
    "build_cli_tools",
    # tools
    "read_file", "write_file", "edit_file", "list_files", "list_tree", "run_shell",
    "web_search", "web_fetch",
    # helpers + bounds (kept exported for consumers that reuse the caps)
    "cap_lines", "clip_line",
    "MAX_LINE_LEN", "READ_LINE_CAP", "LIST_CAP", "SHELL_LINE_CAP", "WEB_LINE_CAP",
    "TREE_DEPTH", "TREE_PER_DIR_CAP", "TREE_TOTAL_CAP",
]
