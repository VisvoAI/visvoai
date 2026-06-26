"""
visvoai.cli.permissions — pre-authorization rules for the permission gate.

The gate (TUI approval, headless deny) asks the user before a mutating tool runs.
A PermissionPolicy lets a project pre-authorize known-safe operations so they run
WITHOUT a prompt — and so a headless run can permit a curated set without --yes.

Configured in `.visvoai/config.toml` (layered global → project, like keys.py):

    [permissions]
    allow_shell = ["git status", "git diff", "ls", "pytest"]   # command prefixes
    allow_write = ["*.md", "docs/**", "notes/*.txt"]           # path globs (rel to cwd)

Matching is conservative: shell rules are prefix matches on the command (so
"git status" allows "git status -s" but not "git push"); write rules are fnmatch
globs against the path the tool was given. No rule → no auto-allow → the gate asks.
"""
from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path
from typing import List

from .keys import global_config_path
from .pathguard import _project_config_path, _read_permissions


class PermissionPolicy:
    """Pre-authorization rules. `auto_allow` returns True when a configured rule
    covers the call — the gate then skips the prompt."""

    def __init__(self, allow_shell: List[str], allow_write: List[str]) -> None:
        self._allow_shell = [s.strip() for s in allow_shell if s.strip()]
        self._allow_write = [g.strip() for g in allow_write if g.strip()]

    def auto_allow(self, tool_name: str, args: dict) -> bool:
        if tool_name == "run_shell":
            cmd = (args.get("command") or "").strip()
            return any(cmd == p or cmd.startswith(p + " ") for p in self._allow_shell)
        if tool_name in ("write_file", "edit_file"):
            path = (args.get("path") or "").strip()
            return bool(path) and any(fnmatch.fnmatch(path, g) for g in self._allow_write)
        return False


def _strlist(table: dict, key: str) -> List[str]:
    raw = table.get(key)
    return [s for s in raw if isinstance(s, str)] if isinstance(raw, list) else []


def load_policy(cwd: str) -> PermissionPolicy:
    """The merged [permissions] policy for cwd (project rules extend global)."""
    allow_shell: List[str] = []
    allow_write: List[str] = []
    for path in (global_config_path(), _project_config_path(cwd)):
        table = _read_permissions(path)
        allow_shell.extend(_strlist(table, "allow_shell"))
        allow_write.extend(_strlist(table, "allow_write"))
    return PermissionPolicy(allow_shell, allow_write)
