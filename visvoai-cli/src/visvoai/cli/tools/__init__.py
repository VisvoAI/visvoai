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
import os
from typing import List, Optional

from langchain_core.tools import BaseTool

from visvoai.cli.tools._common import MAX_LINE_LEN, cap_lines, clip_line
from visvoai.cli.tools.files import (
    LIST_CAP,
    READ_LINE_CAP,
    TREE_DEPTH,
    TREE_PER_DIR_CAP,
    TREE_TOTAL_CAP,
    list_files,
    list_tree,
    make_edit_file,
    make_write_file,
    read_file,
)
from visvoai.cli.tools.shell import SHELL_LINE_CAP, run_shell
from visvoai.cli.tools.web import WEB_LINE_CAP, web_fetch, web_search

# The model sees each tool's docstring verbatim as its description; dedent the
# read-only/shell/web tools' multi-line ones (write/edit are built per-cwd by the
# factories and dedented at build time).
for _t in (read_file, list_files, list_tree, run_shell, web_search, web_fetch):
    _t.description = inspect.cleandoc(_t.description)


def build_cli_tools(cwd: Optional[str] = None) -> List[BaseTool]:
    """Return the standard CLI tool set, with write/edit confined to `cwd` (+ any
    configured extra roots). cwd defaults to the process working directory."""
    from visvoai.cli.pathguard import resolve_roots

    roots = resolve_roots(cwd or os.getcwd())
    write_file = make_write_file(roots)
    edit_file = make_edit_file(roots)
    for _t in (write_file, edit_file):
        _t.description = inspect.cleandoc(_t.description)
    return [read_file, write_file, edit_file, list_files, list_tree, run_shell,
            web_search, web_fetch]


__all__ = [
    "build_cli_tools",
    # tools
    "read_file", "list_files", "list_tree", "run_shell",
    "web_search", "web_fetch",
    # write/edit are built per-cwd via the factories below
    "make_write_file", "make_edit_file",
    # helpers + bounds (kept exported for consumers that reuse the caps)
    "cap_lines", "clip_line",
    "MAX_LINE_LEN", "READ_LINE_CAP", "LIST_CAP", "SHELL_LINE_CAP", "WEB_LINE_CAP",
    "TREE_DEPTH", "TREE_PER_DIR_CAP", "TREE_TOTAL_CAP",
]
