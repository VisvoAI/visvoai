"""Filesystem tools: read_file, write_file, edit_file, list_files, list_tree.

Pure local operations. Reads page with offset/limit; listings cap entries; the
tree view is bounded on depth, per-dir fan-out, and total. All return ERROR: …
as data (never raise) so the agent can recover instead of aborting the turn.
"""
import os
import subprocess
from typing import List, Optional

from langchain_core.tools import tool

from visvoai.cli.tools._common import cap_lines, clip_line

READ_LINE_CAP = 2000     # max lines returned per read_file call
LIST_CAP = 1000          # max entries from list_files

# list_tree bounds — a structure view must be bounded on EVERY axis: depth, per-dir
# fan-out (a single huge dir), and total entries. Plus pruning so we never even
# enter noise/ignored dirs (node_modules, .venv, …).
TREE_DEPTH = 2
TREE_PER_DIR_CAP = 100      # max children shown per directory (fan-out guard)
TREE_TOTAL_CAP = 1000       # max entries across the whole walk
_NOISE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", "target", ".next", ".turbo", ".idea", ".tox",
    "venv", "site-packages", ".egg-info",
}


def _git_tree_paths(abs_path: str) -> Optional[List[str]]:
    """Relative file paths under abs_path that git tracks or doesn't ignore — so
    node_modules/.venv/dist (gitignored) are excluded for free. None if not a repo."""
    try:
        p = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=abs_path, capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return sorted(ln for ln in p.stdout.splitlines() if ln.strip())


def _walk_tree_paths(abs_path: str) -> List[str]:
    """Fallback for non-git dirs: os.walk pruning the hardcoded noise set."""
    out: List[str] = []
    for root, dirs, files in os.walk(abs_path):
        dirs[:] = [d for d in dirs if d not in _NOISE_DIRS]
        rel = os.path.relpath(root, abs_path)
        for f in files:
            out.append(f if rel == "." else f"{rel}/{f}")
        if len(out) > 20000:   # safety bound on a pathological tree
            break
    return sorted(out)


def _render_tree(paths: List[str], depth: int) -> str:
    """Render relative file paths as an indented tree, bounded by depth, a per-dir
    fan-out cap, and a global total cap (each truncation gets a clear marker)."""
    root: dict = {}                       # nested: dir → {child: …}; file → {}
    for p in paths:
        node = root
        for part in [x for x in p.split("/") if x]:
            node = node.setdefault(part, {})
    lines: List[str] = []
    state = {"total": 0, "truncated": False}

    def emit(node: dict, level: int, indent: int) -> None:
        # dirs first (non-empty dict), then files; both alphabetical.
        names = sorted(node.keys(), key=lambda n: (not bool(node[n]), n.lower()))
        for i, name in enumerate(names):
            if state["total"] >= TREE_TOTAL_CAP:
                state["truncated"] = True
                return
            if i >= TREE_PER_DIR_CAP:
                lines.append("  " * indent + f"… ({len(names) - i} more entries)")
                break
            is_dir = bool(node[name])
            lines.append("  " * indent + name + ("/" if is_dir else ""))
            state["total"] += 1
            if is_dir and level < depth:
                emit(node[name], level + 1, indent + 1)

    emit(root, 1, 0)
    body = "\n".join(lines) if lines else "(empty)"
    if state["truncated"]:
        body += f"\n[tree truncated at {TREE_TOTAL_CAP} entries — list a subpath to see more]"
    return body


@tool
def read_file(path: str, offset: int = 1, limit: int = READ_LINE_CAP) -> str:
    """Read a file as numbered lines. For large files this is paginated: it returns
    at most `limit` lines (capped at 2000) starting at the 1-based `offset`, and a
    trailing note tells you the total and how to page (raise `offset`). Over-long
    lines are clipped. Use this to read a window of a big file rather than all of it.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.read().splitlines()
    except OSError as e:
        # Report the failure as data so the agent can recover (retry, try another
        # path) — a raised exception would instead abort the whole turn.
        return f"ERROR: {e}"
    total = len(all_lines)
    if total == 0:
        return "(empty file)"
    start = max(1, offset)
    if start > total:
        return f"ERROR: offset {start} is past end of file ({total} lines)."
    limit = max(1, min(limit, READ_LINE_CAP))
    window = all_lines[start - 1: start - 1 + limit]
    end = start - 1 + len(window)
    body = "\n".join(f"{start + i}\t{clip_line(ln)}" for i, ln in enumerate(window))
    if start > 1 or end < total:
        remaining = total - end
        note = f"[lines {start}–{end} of {total}"
        if remaining > 0:
            note += f"; {remaining} more — re-read with offset={end + 1}"
        note += "]"
        body += f"\n{note}"
    return body


def make_write_file(roots: List[str]):
    """Build a write_file tool confined to `roots` (see pathguard.confine)."""
    from visvoai.cli.pathguard import PathDenied, confine

    @tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file, creating it (and any parent directories) if needed."""
        try:
            abs_path = confine(path, roots)
        except PathDenied as e:
            return f"ERROR: {e}"
        try:
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"ERROR: {e}"
        return f"Wrote {len(content)} chars to {abs_path}"

    return write_file


def make_edit_file(roots: List[str]):
    """Build an edit_file tool confined to `roots` (see pathguard.confine)."""
    from visvoai.cli.pathguard import PathDenied, confine

    @tool
    def edit_file(path: str, old_string: str, new_string: str) -> str:
        """Replace the first occurrence of old_string with new_string in the file at path.

        Returns an error if old_string is not found or if it is ambiguous (appears more than once).
        """
        try:
            abs_path = confine(path, roots)
        except PathDenied as e:
            return f"ERROR: {e}"
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return f"ERROR: {e}"
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {path}. No changes made."
        if count > 1:
            return (
                f"ERROR: old_string appears {count} times in {path} — cannot edit unambiguously. "
                "Provide more surrounding context to make the match unique."
            )
        new_content = content.replace(old_string, new_string, 1)
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            return f"ERROR: {e}"
        return f"Replaced in {abs_path}"

    return edit_file


@tool
def list_files(path: str = ".") -> str:
    """List files and directories at path. Directories are marked with a trailing /."""
    abs_path = os.path.abspath(path)
    try:
        entries = sorted(os.listdir(abs_path))
    except OSError as e:
        return f"ERROR: {e}"
    lines = []
    for entry in entries:
        full = os.path.join(abs_path, entry)
        lines.append(entry + ("/" if os.path.isdir(full) else ""))
    return cap_lines("\n".join(lines), LIST_CAP) if lines else "(empty)"


@tool
def list_tree(path: str = ".", depth: int = TREE_DEPTH) -> str:
    """Show the directory STRUCTURE as an indented tree (dirs marked with '/').

    Recursive but bounded on every axis: `depth` levels deep, at most 100 children
    per directory, 1000 entries total — each truncation is marked. Ignored/noise
    dirs (node_modules, .venv, dist, .git, …) are skipped via .gitignore in a repo,
    or a built-in noise set otherwise. To see a truncated branch, call again with
    that subpath. Prefer this over `ls -R`/`find` for getting your bearings."""
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        return f"ERROR: not a directory: {path}"
    depth = max(1, min(depth, 8))
    paths = _git_tree_paths(abs_path)
    if paths is None:
        paths = _walk_tree_paths(abs_path)
    return _render_tree(paths, depth)
