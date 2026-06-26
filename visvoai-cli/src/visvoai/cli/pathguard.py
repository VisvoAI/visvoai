"""
visvoai.cli.pathguard — confine file mutations to allowed roots.

A hard boundary, NOT a prompt: write_file / edit_file resolve their target through
`confine()`, which rejects anything outside the allowed roots. Symlinks and `..`
are resolved BEFORE the containment check, so neither can escape. Default root is
the launch cwd; extra roots are opt-in via `.visvoai/config.toml`:

    [permissions]
    write_roots = ["../sibling-lib", "/abs/shared"]   # relative entries anchor to cwd

Reads are intentionally NOT confined (the writes-only policy). run_shell cannot be
meaningfully confined here — it is a shell — so it is governed by the permission
gate, not by this module.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import List

from .keys import global_config_path


class PathDenied(Exception):
    """Raised when a path resolves outside the allowed roots (or into a blocked
    location). Tools catch this and return it as ERROR text — never propagate."""


def _project_config_path(cwd: str) -> Path:
    """`<project>/.visvoai/config.toml`, anchored to the nearest .visvoai/ walking
    up from cwd (falls back to cwd/.visvoai). Project shares one config file with
    context.toml's sibling — permissions live under [permissions]."""
    start = Path(cwd).resolve()
    for d in (start, *start.parents):
        if (d / ".visvoai").is_dir():
            return d / ".visvoai" / "config.toml"
    return start / ".visvoai" / "config.toml"


def _read_permissions(path: Path) -> dict:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    table = data.get("permissions")
    return table if isinstance(table, dict) else {}


def _extra_write_roots(cwd: str) -> List[str]:
    """Configured extra write roots (global then project), each anchored to cwd if
    relative. Malformed/missing config yields none."""
    roots: List[str] = []
    for path in (global_config_path(), _project_config_path(cwd)):
        raw = _read_permissions(path).get("write_roots")
        if isinstance(raw, list):
            roots.extend(str(r) for r in raw if isinstance(r, str))
    resolved = []
    for r in roots:
        anchored = r if os.path.isabs(r) else os.path.join(cwd, r)
        resolved.append(os.path.realpath(anchored))
    return resolved


def resolve_roots(cwd: str) -> List[str]:
    """The allowed write roots: the launch cwd first, then any configured extras.
    All realpath-resolved so the containment check compares canonical paths."""
    return [os.path.realpath(cwd), *_extra_write_roots(cwd)]


def confine(path: str, roots: List[str]) -> str:
    """Resolve `path` (relative entries against the first root = cwd) and return its
    canonical absolute form, guaranteed within one of `roots`. Raises PathDenied if
    it escapes the roots or targets a .git internal directory.

    Symlinks and `..` are resolved first via realpath, so a symlink pointing out of
    the root, or a `../../etc/passwd`, is caught."""
    if not roots:
        raise PathDenied("no write roots configured")
    base = roots[0]
    target = path if os.path.isabs(path) else os.path.join(base, path)
    real = os.path.realpath(target)

    within = any(real == r or real.startswith(r + os.sep) for r in roots)
    if not within:
        raise PathDenied(
            f"path '{path}' is outside the allowed roots (resolved to {real}). "
            "Writes are confined to the working directory."
        )
    # Block writing into git's internals — corrupting .git is destructive and never
    # a legitimate edit target.
    parts = os.path.relpath(real, base).split(os.sep)
    if ".git" in parts:
        raise PathDenied(f"path '{path}' is inside a .git directory — refusing to write.")
    return real
