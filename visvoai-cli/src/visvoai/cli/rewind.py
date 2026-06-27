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

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.containers import VerticalScroll

from visvoai.cli import store
from visvoai.cli.checkpoints import CheckpointError, ShadowRepo
from visvoai.cli.screens import RewindScreen
from visvoai.cli.widgets import SystemNote


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_iso(s: str | None) -> str:
    if not s:
        return ""
    try:
        return store._relative(datetime.fromisoformat(s))
    except (ValueError, TypeError):
        return ""


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
            # A ref per checkpoint commit keeps EVERY snapshot permanently reachable —
            # so a later rewind/branch can never strand a commit (gc-safe), and an
            # abandoned timeline's code stays recoverable. Plus the moving branch tip.
            repo.ref_set(f"refs/visvoai/{self._conv_id}/cp/{rec['id']}", sha)
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

    # ── resume drift (Plan D) ─────────────────────────────────────────────────
    def _resume_checkpoints(self) -> None:
        """On resuming a conversation, adopt its checkpoint tip and — if the work tree
        drifted since the last snapshot (hand edits, pull, branch switch, a build) —
        record a 'baseline' of the current reality at the thread's end. That keeps the
        timeline continuous and lets `_rewind_crosses_baseline` warn before a rewind
        discards out-of-session changes."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        records = store.read_checkpoints(self._project_id, self._conv_id)
        if not records:   # pre-feature conversation → the first turn lays the baseline
            return
        self._load_checkpoint_tip(records)
        try:
            if self._cp_tip_sha and repo.is_dirty(self._cp_tip_sha):
                self._record_checkpoint(len(self._history), "baseline",
                                        "resumed (external changes)")
        except CheckpointError:
            pass

    # ── rewind (Plan C) ───────────────────────────────────────────────────────
    def _active_chain(self, records: list[dict]) -> list[dict]:
        """The active branch's checkpoints in chronological order (baseline … tip),
        walked via parent links from the current tip (fallback: the last record)."""
        by_id = {r["id"]: r for r in records}
        node = by_id.get(self._cp_tip_id) or (records[-1] if records else None)
        chain: list[dict] = []
        seen: set[str] = set()
        while node is not None and node["id"] not in seen:
            chain.append(node)
            seen.add(node["id"])
            node = by_id.get(node.get("parent"))
        chain.reverse()
        return chain

    def action_open_rewind(self) -> None:
        self.run_worker(self._rewind_flow())

    async def _rewind_flow(self) -> None:
        """`/rewind` (Ctrl+B) — pick an earlier checkpoint; on confirm, restore the
        files to it and truncate the conversation to match."""
        if self._project_id is None or self._conv_id is None:
            self.notify("nothing to rewind yet", severity="warning")
            return
        records = store.read_checkpoints(self._project_id, self._conv_id)
        if not records:
            self.notify("no checkpoints yet — run a turn first", severity="warning")
            return
        repo = self._ensure_checkpoints()
        chain = self._active_chain(records)
        tip_commit = self._cp_tip_sha
        entries: list[dict] = []
        for cp in reversed(chain[:-1]):   # everything before the current tip, newest-first
            files = None
            if repo and tip_commit:
                try:
                    files = len(repo.diff_names(cp["commit"], tip_commit))
                except CheckpointError:
                    files = None
            entries.append({**cp, "files": files, "when": _relative_iso(cp.get("created"))})
        if not entries:
            self.notify("nothing earlier to rewind to", severity="warning")
            return
        cid = await self.push_screen_wait(RewindScreen(entries))
        if not cid:
            return
        cp = next((c for c in records if c["id"] == cid), None)
        if cp is None:
            return
        warn = self._rewind_crosses_baseline(chain, cp)
        prompt = (f"Rewind to “{cp['label'] or 'start'}”? Files and conversation after "
                  f"this point are discarded.")
        if warn:
            prompt += " ⚠ This also discards changes made outside this session."
        idx, _ = await self.ask_choice(prompt, ["Rewind", "Cancel"])
        if idx != 0:
            return
        await self._apply_rewind(cp)

    def _rewind_crosses_baseline(self, chain: list[dict], target: dict) -> bool:
        """True if any 'baseline' checkpoint (a resume point capturing external edits)
        sits strictly AFTER the target in the active chain — rewinding past it discards
        changes made outside the session, which warrants a louder warning (Plan D)."""
        seen_target = False
        for cp in chain:
            if cp["id"] == target["id"]:
                seen_target = True
                continue
            if seen_target and cp.get("kind") == "baseline":
                return True
        return False

    def _completed_turns(self, msgs: list) -> int:
        """How many receipts to keep after a truncation: one per COMPLETED turn. A
        thread ending on a human turn or an unanswered tool batch has an open last
        turn (no receipt yet)."""
        humans = sum(1 for m in msgs if isinstance(m, HumanMessage))
        if not msgs:
            return 0
        last = msgs[-1]
        incomplete = (isinstance(last, (HumanMessage, ToolMessage))
                      or (isinstance(last, AIMessage) and last.tool_calls))
        return max(0, humans - (1 if incomplete else 0))

    async def _apply_rewind(self, cp: dict) -> None:
        """Restore files to `cp`, truncate the thread + receipts to its message index,
        move the active tip, replay the trimmed thread, and drop a marker."""
        repo = self._ensure_checkpoints()
        if repo is not None:
            try:
                repo.restore(cp["commit"])
            except CheckpointError as e:
                self.notify(f"could not restore files: {e}", severity="error")
                return
        idx = cp["message_index"]
        self._history = self._history[:idx]
        store.save_conversation(self._project_id, self._conv_id, self._history)
        self._persisted_count = len(self._history)
        store.truncate_receipts(self._project_id, self._conv_id,
                                self._completed_turns(self._history))
        # Move the active tip back; the abandoned commits stay reachable via their
        # per-checkpoint refs, so the discarded code is still recoverable.
        self._cp_tip_id = cp["id"]
        self._cp_tip_sha = cp["commit"]
        self._cp_branch = cp.get("branch", "main")
        self._cp_branch_tips[self._cp_branch] = cp["id"]
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=self._cp_branch, branch_tips=self._cp_branch_tips)
            if repo is not None:
                repo.ref_set(f"refs/visvoai/{self._conv_id}/{self._cp_branch}", cp["commit"])
        except (CheckpointError, OSError):
            pass
        await self._replay_history(self._history)
        log = self.query_one("#log", VerticalScroll)
        await log.mount(SystemNote(
            f"rewound to “{cp['label'] or 'start'}” — files and conversation restored",
            kind="branch"))
        log.scroll_end(animate=False)
