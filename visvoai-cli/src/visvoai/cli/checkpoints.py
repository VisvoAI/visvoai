"""checkpoints.py — a shadow git repo: working-tree snapshots that never touch the
user's own `.git`.

The repo lives at `$VISVOAI_HOME/projects/<pid>/checkpoints.git` and its *work tree*
is the project root (see `store.project_root`). Each snapshot is a real git commit
built with plumbing (`add -A` → `write-tree` → `commit-tree`), so we control the DAG
(explicit parent) and never disturb a checked-out branch. This captures the WHOLE
tree — including changes a shell command made — for free, and content-addressing
dedupes blobs across every turn and conversation.

Why a separate GIT_DIR with an external GIT_WORK_TREE (the "shadow repo"): it tracks
the user's files without creating a second checkout and without ever reading or
writing their `.git`. It works even when the project is not a git repo at all.

Pure subprocess so tests can run against a throwaway repo. `available()` is False when
git is missing → callers skip checkpointing rather than break a turn.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from visvoai.cli import store

# Layered on top of the work tree's own .gitignore — so a project with no .gitignore
# still never snapshots dependency/build dirs or our own metadata (incl. secrets).
_DEFAULT_EXCLUDES = [
    ".git/", ".visvoai/", "node_modules/", ".venv/", "venv/", "__pycache__/",
    ".mypy_cache/", ".pytest_cache/", ".ruff_cache/", "dist/", "build/",
    "*.pyc", ".DS_Store",
]


class CheckpointError(RuntimeError):
    """A git plumbing call failed. Callers degrade gracefully — checkpointing must
    never crash a turn."""


class ShadowRepo:
    """A shadow git repo over a project's work tree. One per project (shared, deduped
    blob store); conversations isolate logically via ref namespaces, not separate repos."""

    def __init__(self, git_dir: Path, work_tree: Path) -> None:
        self.git_dir = Path(git_dir)
        self.work_tree = Path(work_tree)

    # ── construction ──────────────────────────────────────────────────────────
    @classmethod
    def for_project(cls, project_id: str, cwd: str) -> "ShadowRepo":
        """Resolve paths for `project_id` and ensure the repo exists. The work tree is
        the project root so snapshots are stable across launch subdirs."""
        git_dir = store.visvoai_home() / "projects" / project_id / "checkpoints.git"
        repo = cls(git_dir, store.project_root(cwd))
        repo.ensure_init()
        return repo

    @staticmethod
    def available() -> bool:
        return shutil.which("git") is not None

    # ── low-level ───────────────────────────────────────────────────────────────
    def _run(self, *args: str, check: bool = True) -> str:
        """Run `git --git-dir … --work-tree … <args>` from the work tree. Returns
        stdout (stripped). Raises CheckpointError on failure when `check`."""
        try:
            p = subprocess.run(
                ["git", "--git-dir", str(self.git_dir), "--work-tree", str(self.work_tree), *args],
                cwd=str(self.work_tree), capture_output=True, text=True, timeout=60,
            )
        except Exception as e:  # boundary: external process — surface as our error
            raise CheckpointError(f"git {args[0] if args else ''} failed to launch: {e}") from e
        if check and p.returncode != 0:
            raise CheckpointError(f"git {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
        return p.stdout.strip()

    def ensure_init(self) -> None:
        """Create the bare-ish shadow repo (idempotent) and stamp an identity + a
        default excludes file. The repo is 'bare' (no work tree of its own) but we drive
        it with --work-tree, so it operates on the project tree."""
        if (self.git_dir / "HEAD").exists():
            return
        self.git_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "init", "--bare", "-q", str(self.git_dir)],
                           capture_output=True, text=True, timeout=30, check=True)
        except Exception as e:
            raise CheckpointError(f"could not init shadow repo: {e}") from e
        self._run("config", "user.name", "visvoai")
        self._run("config", "user.email", "checkpoints@visvoai.local")
        # Don't choke on a pre-existing index lock from a crashed run.
        excludes = self.git_dir / "info" / "excludes"
        excludes.parent.mkdir(parents=True, exist_ok=True)
        excludes.write_text("\n".join(_DEFAULT_EXCLUDES) + "\n", encoding="utf-8")
        self._run("config", "core.excludesFile", str(excludes))

    # ── snapshot / restore ───────────────────────────────────────────────────────
    def tree_of(self, sha: str) -> str:
        return self._run("rev-parse", f"{sha}^{{tree}}")

    def snapshot(self, parent_sha: Optional[str], message: str) -> Tuple[str, bool]:
        """Capture the current work tree as a commit (parent = `parent_sha`). Returns
        `(commit_sha, created_new)`. If the staged tree is identical to the parent's
        tree, NO commit is made — returns `(parent_sha, False)` (content-addressed
        dedup), so a no-change turn costs nothing."""
        self._run("add", "-A")
        tree = self._run("write-tree")
        if parent_sha and self.tree_of(parent_sha) == tree:
            return parent_sha, False
        args = ["commit-tree", tree, "-m", message]
        if parent_sha:
            args += ["-p", parent_sha]
        return self._run(*args), True

    def restore(self, target_sha: str) -> None:
        """Make the work tree EXACTLY match `target_sha` (TRUE restore): revert modified
        files, restore deleted ones, and DELETE files created since (scoped to the
        tracked tree — never a blind clean of the whole cwd). `add -A` first so the
        delete-set is computed against the live tree (captures drift)."""
        self._run("add", "-A")
        live = set(self._run("ls-files").splitlines())
        target = set(self._run("ls-tree", "-r", "--name-only", target_sha).splitlines())
        self._run("read-tree", target_sha)
        self._run("checkout-index", "-a", "-f")
        for rel in sorted(live - target):
            p = self.work_tree / rel
            try:
                p.unlink()
            except OSError:
                continue
            # Best-effort: prune now-empty parent dirs up to (not including) the root.
            parent = p.parent
            while parent != self.work_tree and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent

    # ── refs (keep commits reachable so gc never prunes them) ─────────────────────
    def ref_set(self, name: str, sha: str) -> None:
        self._run("update-ref", name, sha)

    def ref_get(self, name: str) -> Optional[str]:
        out = self._run("rev-parse", "--verify", "--quiet", name, check=False)
        return out or None

    def ref_delete(self, name: str) -> None:
        self._run("update-ref", "-d", name, check=False)

    def refs(self, prefix: str) -> Dict[str, str]:
        """{full_ref_name: sha} for every ref under `prefix` (e.g. 'refs/visvoai/<cid>/')."""
        out = self._run("for-each-ref", "--format=%(refname) %(objectname)", prefix, check=False)
        result: Dict[str, str] = {}
        for line in out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                result[parts[0]] = parts[1]
        return result

    # ── worktree (fork) / bundle (export) ─────────────────────────────────────────
    def add_worktree(self, path: str, sha: str) -> None:
        """Materialize `sha` as a detached linked worktree at `path` (a second working
        dir) — the primitive behind fork-the-session."""
        self._run("worktree", "add", "--detach", str(path), sha)

    def remove_worktree(self, path: str) -> None:
        self._run("worktree", "remove", "--force", str(path), check=False)

    def bundle(self, out_path: str, refs: List[str]) -> None:
        """Pack the given refs (and their reachable history) into a single portable
        `.bundle` file — the code half of a 'full' conversation export."""
        if not refs:
            raise CheckpointError("bundle needs at least one ref")
        self._run("bundle", "create", str(out_path), *refs)
