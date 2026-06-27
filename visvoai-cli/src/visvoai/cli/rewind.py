"""rewind.py — RewindMixin: git-structured conversation history.

Records a working-tree checkpoint per tool BATCH (before the batch runs, while the
tree is quiescent — parallel tools share no mid-batch moment) and at turn end, each
mapped to a message index so code and conversation rewind together. Built on the
shadow repo (`checkpoints.ShadowRepo`); checkpoint records are the conversation↔code
mapping (`store.append_checkpoint`), the code DAG itself is shadow-repo commits.

This half is the recording path. Rewind / branch / fork / export flows are added in
later phases of the same mixin. Mixed into VisvoApp; calls turn primitives via self.

Design notes:
- Checkpoint = {id, message_index, parent, commit, kind, branch, label, created}.
  `commit` is the shadow-repo commit sha; `message_index` is the thread length to
  truncate to when rewinding here.
- kinds: "baseline" (conversation floor / resume drift), "pre_batch" (before a tool
  batch — message_index excludes the requesting AIMessage so the model re-plans),
  "turn" (end of a turn).
- Checkpointing must NEVER break a turn: any CheckpointError/OSError is swallowed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from visvoai.cli import store
from visvoai.cli.checkpoints import CheckpointError, ShadowRepo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RewindMixin:
    """Checkpoint recording (+ rewind/branch/fork/export, added in later phases)."""

    # ── repo lifecycle ────────────────────────────────────────────────────────
    def _ensure_checkpoints(self) -> ShadowRepo | None:
        """Lazily build the project's shadow repo. None when git is missing, the
        conversation isn't resolved yet, or init failed (then we never retry)."""
        if self._checkpoints is not None or self._cp_failed:
            return self._checkpoints
        if not ShadowRepo.available():
            self._cp_failed = True
            return None
        if self._project_id is None or self._conv_id is None:
            return None
        try:
            self._checkpoints = ShadowRepo.for_project(self._project_id, self._cwd)
        except CheckpointError:
            self._cp_failed = True
            return None
        return self._checkpoints

    def _load_checkpoint_tip(self, records: list[dict]) -> None:
        """Resume: adopt the active branch + its tip from meta (fallback: last record),
        so the next snapshot chains onto the existing DAG instead of re-baselining."""
        meta = store.read_meta(self._project_id, self._conv_id)
        self._cp_branch = meta.get("active_branch", "main")
        self._cp_branch_tips = dict(meta.get("branch_tips", {}))
        tip_id = self._cp_branch_tips.get(self._cp_branch)
        rec = next((r for r in reversed(records) if r["id"] == tip_id), records[-1])
        self._cp_tip_id = rec["id"]
        self._cp_tip_sha = rec["commit"]

    # ── recording ─────────────────────────────────────────────────────────────
    def _record_checkpoint(self, message_index: int, kind: str, label: str) -> None:
        """Snapshot the work tree and append a checkpoint record at `message_index`.
        No-op (swallowed) if checkpointing is unavailable — never breaks a turn."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        try:
            sha, _made = repo.snapshot(self._cp_tip_sha, label or kind)
        except CheckpointError:
            return
        rec = {
            "id": uuid.uuid4().hex[:8],
            "message_index": message_index,
            "parent": self._cp_tip_id,
            "commit": sha,
            "kind": kind,
            "branch": self._cp_branch,
            "label": (label or "")[:80],
            "created": _now_iso(),
        }
        try:
            store.append_checkpoint(self._project_id, self._conv_id, rec)
            repo.ref_set(f"refs/visvoai/{self._conv_id}/{self._cp_branch}", sha)
        except (CheckpointError, OSError):
            return
        self._cp_tip_id = rec["id"]
        self._cp_tip_sha = sha
        self._cp_branch_tips[self._cp_branch] = rec["id"]
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=self._cp_branch,
                             branch_tips=self._cp_branch_tips)
        except OSError:
            pass

    def _maybe_baseline(self) -> None:
        """Once per conversation, before the first turn does any work: record a
        'baseline' of the pristine tree (the rewind floor). On a resumed conversation
        that already has checkpoints, adopt its tip instead of re-baselining."""
        if self._cp_tip_id is not None:   # chain already live this session
            return
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        existing = store.read_checkpoints(self._project_id, self._conv_id)
        if existing:
            self._load_checkpoint_tip(existing)
            return
        self._record_checkpoint(0, "baseline", "start")
