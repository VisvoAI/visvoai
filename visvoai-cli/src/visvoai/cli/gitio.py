"""gitio.py — real git working-tree reads + commit for the GitScreen.

Produces the same status dict shape GitScreen renders (branch, ahead/behind,
staged+unstaged file rows with +/- counts and a parsed per-file diff), and
performs stage / unstage / commit. Kept side-effect-thin and pure-subprocess so
tests can monkeypatch these functions without touching a real repo.

Maps 1:1 onto `visvoai/cli/gitio.py` at the Phase-7 package migration.
"""
from __future__ import annotations

import os
import subprocess
from typing import List, Optional, Tuple

# Porcelain status letter → chip palette key (others fall back to muted).
_TRACKED_STATES = {"M", "A", "D", "R", "C", "T"}


def _run(cwd: str, args: List[str], timeout: float = 3) -> Tuple[int, str, str]:
    """Run `git <args>` in cwd. Returns (returncode, stdout, stderr); (-1, "", msg)
    on failure to even launch (not a repo, git missing, timeout)."""
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # boundary: external process — surface, don't crash the UI
        return -1, "", str(e)


def _is_repo(cwd: str) -> bool:
    rc, out, _ = _run(cwd, ["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


def _branch(cwd: str) -> str:
    rc, out, _ = _run(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if rc == 0 and out.strip() else "HEAD"


def _upstream_counts(cwd: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """(upstream_ref, behind, ahead) — or (None, None, None) when no upstream is set."""
    rc, out, _ = _run(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    if rc != 0 or not out.strip():
        return None, None, None
    upstream = out.strip()
    rc, out, _ = _run(cwd, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    if rc != 0 or "\t" not in out:
        return upstream, None, None
    behind, ahead = out.split("\t", 1)
    try:
        return upstream, int(behind), int(ahead)
    except ValueError:
        return upstream, None, None


def _numstat(cwd: str, cached: bool) -> dict[str, Tuple[int, int]]:
    """path → (adds, dels) for staged (cached) or unstaged tracked changes.
    Binary files report '-' for both → recorded as (0, 0)."""
    args = ["diff", "--numstat"] + (["--cached"] if cached else [])
    rc, out, _ = _run(cwd, args)
    counts: dict[str, Tuple[int, int]] = {}
    if rc != 0:
        return counts
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        # Renames render as "old => new" (or "{a => b}/c"); take the new path.
        if "=>" in path:
            path = path.split("=>")[-1].strip().strip("}").strip()
        adds = int(a) if a.isdigit() else 0
        dels = int(d) if d.isdigit() else 0
        counts[path] = (adds, dels)
    return counts


def _split_diffs(text: str) -> dict[str, List[Tuple[str, str]]]:
    """Split a multi-file unified diff into {path: [(kind, text)]} where kind is
    'add' | 'del' | 'ctx'. Git noise (diff/index/+++/---/@@) is dropped."""
    out: dict[str, List[Tuple[str, str]]] = {}
    path: Optional[str] = None
    rows: List[Tuple[str, str]] = []

    def _flush() -> None:
        if path is not None:
            out[path] = rows

    for line in text.splitlines():
        if line.startswith("diff --git "):
            _flush()
            path, rows = None, []
            continue
        if line.startswith("+++ "):
            p = line[4:]
            if p != "/dev/null":
                path = p[2:] if p.startswith("b/") else p
            continue
        if line.startswith("--- "):
            # Deletions have +++ /dev/null → fall back to the a/ path.
            p = line[4:]
            if path is None and p != "/dev/null":
                path = p[2:] if p.startswith("a/") else p
            continue
        if line.startswith(("index ", "@@", "new file", "deleted file",
                            "rename ", "similarity ", "old mode", "new mode",
                            "Binary ", "\\ No newline")):
            continue
        if line.startswith("+"):
            rows.append(("add", line[1:]))
        elif line.startswith("-"):
            rows.append(("del", line[1:]))
        elif line.startswith(" "):
            rows.append(("ctx", line[1:]))
    _flush()
    return out


def _untracked_change(cwd: str, path: str) -> dict:
    """Build an all-adds change row for an untracked file (no git diff exists yet)."""
    full = os.path.join(cwd, path)
    rows: List[Tuple[str, str]] = []
    adds = 0
    try:
        with open(full, "r", errors="replace") as fh:
            for line in fh.read().splitlines():
                rows.append(("add", line))
                adds += 1
    except (OSError, UnicodeError):
        rows = []  # binary / unreadable → no preview
    return {"path": path, "state": "?", "staged": False, "adds": adds, "dels": 0, "diff": rows}


def _porcelain_entries(cwd: str) -> List[Tuple[str, str, str]]:
    """(X, Y, path) per changed file from `git status --porcelain -z`. Renames
    consume their second (origin) field; the new path is what we surface."""
    rc, out, _ = _run(cwd, ["status", "--porcelain", "--untracked-files=all", "-z"])
    if rc != 0:
        return []
    tokens = out.split("\0")
    entries: List[Tuple[str, str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok or len(tok) < 3:
            i += 1
            continue
        x, y, path = tok[0], tok[1], tok[3:]
        if x == "R" or y == "R":  # rename: next token is the origin path — skip it
            i += 1
        entries.append((x, y, path))
        i += 1
    return entries


def working_tree_status(cwd: str) -> Optional[dict]:
    """The GitScreen status dict for cwd, or None if not a repo or the tree is
    clean. A file with both staged and unstaged changes yields two rows (one per
    section), matching git's model."""
    if not _is_repo(cwd):
        return None

    entries = _porcelain_entries(cwd)
    if not entries:
        return None

    staged_counts = _numstat(cwd, cached=True)
    unstaged_counts = _numstat(cwd, cached=False)
    staged_diffs = _split_diffs(_run(cwd, ["diff", "--cached"])[1])
    unstaged_diffs = _split_diffs(_run(cwd, ["diff"])[1])

    files: List[dict] = []
    for x, y, path in entries:
        if x == "?" and y == "?":
            files.append(_untracked_change(cwd, path))
            continue
        if x in _TRACKED_STATES:  # staged change present
            a, d = staged_counts.get(path, (0, 0))
            files.append({"path": path, "state": x, "staged": True,
                          "adds": a, "dels": d, "diff": staged_diffs.get(path, [])})
        if y in _TRACKED_STATES:  # unstaged change present
            a, d = unstaged_counts.get(path, (0, 0))
            files.append({"path": path, "state": y, "staged": False,
                          "adds": a, "dels": d, "diff": unstaged_diffs.get(path, [])})

    upstream, behind, ahead = _upstream_counts(cwd)
    return {
        "branch": _branch(cwd),
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "files": files,
        "suggested_message": "",
    }


def project_files(cwd: str, limit: int = 4000) -> List[str]:
    """Candidate paths for the @-mention picker: git-tracked + untracked (respecting
    .gitignore). Falls back to a bounded recursive walk when cwd is not a repo."""
    rc, out, _ = _run(cwd, ["ls-files", "--cached", "--others", "--exclude-standard"])
    if rc == 0:
        return [p for p in out.splitlines() if p][:limit]
    # Not a git repo → walk with the usual noise dirs pruned.
    skip = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}
    paths: List[str] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            paths.append(os.path.relpath(os.path.join(root, f), cwd))
            if len(paths) >= limit:
                return paths
    return paths


def stage(cwd: str, path: str) -> bool:
    return _run(cwd, ["add", "--", path])[0] == 0


def unstage(cwd: str, path: str) -> bool:
    rc = _run(cwd, ["restore", "--staged", "--", path])[0]
    if rc != 0:  # older git without `restore`
        rc = _run(cwd, ["reset", "-q", "HEAD", "--", path])[0]
    return rc == 0


def commit(cwd: str, subject: str, body: str = "") -> Tuple[bool, str]:
    """Commit the staged index. `subject` is the summary line; `body` (optional) is
    the long description — passed as a second `-m` so git writes the standard
    'subject\\n\\nbody' form. Returns (ok, detail); detail is git's stderr on failure
    (e.g. nothing staged, hook rejection)."""
    args = ["commit", "-m", subject]
    if body:
        args += ["-m", body]
    rc, out, err = _run(cwd, args)
    return rc == 0, (err or out).strip()
