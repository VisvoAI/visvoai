"""rewind.py — RewindMixin: git-structured conversation history.

Records a working-tree checkpoint per tool BATCH (before the batch runs, while the
tree is quiescent — parallel tools share no mid-batch moment) and at turn end, each
mapped to a message index so code and conversation rewind together.

Two-level storage (see store.py):
- the conversation owns the immutable REGISTRY (`checkpoints.jsonl`: checkpoint id →
  shadow commit) — the code mapping only;
- each branch owns its own TIMELINE (`branches/<name>/timeline.jsonl`: ordered rows
  {checkpoint_id, message_index, kind, label}) — its turn/tool→checkpoint view.

A branch reconstructs itself ONLY from its own folder; it resolves a checkpoint id
against the shared registry but never reads another branch's mutable state. Fork =
deep-copy a branch folder (+ truncate); `forked_from` is provenance, never a
reconstruction path. Checkpointing is best-effort: any CheckpointError/OSError is
swallowed so it never breaks a turn.

Flows: /rewind (Ctrl+B) restore-or-branch · /branch switch/fork · /fork worktree ·
/export transcript|bundle · /log the chain. Mixed into VisvoApp; uses turn primitives
via self.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.containers import VerticalScroll

from visvoai.cli import agent, store
from visvoai.cli.checkpoints import CheckpointError, ShadowRepo
from visvoai.cli.screens import BranchScreen, RewindScreen
from visvoai.cli.screens.branch_view import NEW_BRANCH
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


def _truncate_to(rows: list[dict], checkpoint_id: str) -> list[dict]:
    """Timeline rows up to AND INCLUDING the row for `checkpoint_id` (the new tip)."""
    keep: list[dict] = []
    for r in rows:
        keep.append(r)
        if r["checkpoint_id"] == checkpoint_id:
            break
    return keep


class RewindMixin:
    """Checkpoint recording + rewind / branch / switch / fork / export."""

    def _branch_ref(self, branch: str) -> str:
        return f"refs/visvoai/{self._conv_id}/{branch}"

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

    def _load_checkpoint_tip(self) -> None:
        """Adopt the active branch + its tip (from branch meta → registry commit), so
        the next snapshot chains onto the existing timeline."""
        self._cp_branch = store.active_branch(self._project_id, self._conv_id)
        bm = store.read_branch_meta(self._project_id, self._conv_id, self._cp_branch)
        tip = bm.get("tip")
        self._cp_tip_id = tip
        self._cp_tip_sha = (store.registry_commit(self._project_id, self._conv_id, tip)
                            if tip else None)

    # ── recording ─────────────────────────────────────────────────────────────
    def _record_checkpoint(self, message_index: int, kind: str, label: str) -> None:
        """Snapshot the work tree, register `id → commit`, and append a timeline row to
        the active branch. No-op (swallowed) if checkpointing is unavailable."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        try:
            sha, _made = repo.snapshot(self._cp_tip_sha, label or kind)
        except CheckpointError:
            return
        cp_id = uuid.uuid4().hex[:8]
        row = {"checkpoint_id": cp_id, "message_index": message_index,
               "kind": kind, "label": (label or "")[:80], "created": _now_iso()}
        try:
            store.append_registry(self._project_id, self._conv_id, cp_id, sha)
            store.append_timeline(self._project_id, self._conv_id, self._cp_branch, row)
            store.write_branch_meta(self._project_id, self._conv_id, self._cp_branch, tip=cp_id)
            # A ref per checkpoint commit keeps EVERY snapshot reachable (gc-safe) so a
            # later rewind/branch can never strand a commit; plus the moving branch tip.
            repo.ref_set(f"refs/visvoai/{self._conv_id}/cp/{cp_id}", sha)
            repo.ref_set(self._branch_ref(self._cp_branch), sha)
        except (CheckpointError, OSError):
            return
        self._cp_tip_id = cp_id
        self._cp_tip_sha = sha

    def _maybe_baseline(self) -> None:
        """Once per conversation, before the first turn does any work: record a
        'baseline' of the pristine tree (the rewind floor). On a resumed conversation
        that already has a timeline, adopt its tip instead."""
        if self._cp_tip_id is not None:
            return
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        store.ensure_branch(self._project_id, self._conv_id, self._cp_branch)
        # Establish conversation-level active_branch (the turn path also stamps it, but
        # the baseline may be the first thing to touch a brand-new conversation).
        store.write_meta(self._project_id, self._conv_id, active_branch=self._cp_branch)
        if store.read_timeline(self._project_id, self._conv_id, self._cp_branch):
            self._load_checkpoint_tip()
            return
        self._record_checkpoint(0, "baseline", "start")

    # ── resume drift (Plan D) ─────────────────────────────────────────────────
    def _resume_checkpoints(self) -> None:
        """On resume, adopt the active branch's tip and — if the work tree drifted since
        the last snapshot — record a 'baseline' of current reality at the thread's end,
        so `_rewind_crosses_baseline` can warn before a rewind discards external edits."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return
        self._cp_branch = store.active_branch(self._project_id, self._conv_id)
        if not store.read_timeline(self._project_id, self._conv_id, self._cp_branch):
            return   # no checkpoints yet → the first turn lays the baseline
        self._load_checkpoint_tip()
        try:
            if self._cp_tip_sha and repo.is_dirty(self._cp_tip_sha):
                self._record_checkpoint(len(self._history), "baseline",
                                        "resumed (external changes)")
        except CheckpointError:
            pass

    # ── rewind (Plan C) ───────────────────────────────────────────────────────
    def _timeline(self) -> list[dict]:
        return store.read_timeline(self._project_id, self._conv_id, self._cp_branch)

    def _picker_entries(self, rows: list[dict], *, with_files: bool) -> list[dict]:
        """RewindScreen rows (newest-first). `with_files` adds a diff-count vs the
        current tip (skipped for branch/fork pickers where it isn't meaningful)."""
        repo = self._ensure_checkpoints() if with_files else None
        tip_commit = self._cp_tip_sha
        entries: list[dict] = []
        for row in reversed(rows):
            files = None
            if repo and tip_commit:
                commit = store.registry_commit(self._project_id, self._conv_id, row["checkpoint_id"])
                if commit:
                    try:
                        files = len(repo.diff_names(commit, tip_commit))
                    except CheckpointError:
                        files = None
            entries.append({"id": row["checkpoint_id"], "label": row["label"],
                            "kind": row["kind"], "message_index": row["message_index"],
                            "files": files, "when": _relative_iso(row.get("created"))})
        return entries

    def action_open_rewind(self) -> None:
        self.run_worker(self._rewind_flow())

    async def _rewind_flow(self) -> None:
        """`/rewind` (Ctrl+B) — pick an earlier checkpoint; restore to it, or branch."""
        if self._project_id is None or self._conv_id is None:
            self.notify("Nothing to rewind yet — checkpoints are saved as you work.", severity="warning")
            return
        rows = self._timeline()
        if len(rows) < 2:
            self.notify("No earlier checkpoints yet — one is saved at the end of each turn.", severity="warning")
            return
        entries = self._picker_entries(rows[:-1], with_files=True)   # exclude the current tip
        cid = await self.push_screen_wait(RewindScreen(entries))
        if not cid:
            return
        row = next((r for r in rows if r["checkpoint_id"] == cid), None)
        if row is None:
            return
        prompt = f"Go back to “{row['label'] or 'start'}”?"
        if self._rewind_crosses_baseline(rows, cid):
            prompt += " ⚠ Rewinding past here also discards changes made outside this session."
        idx, _ = await self.ask_choice(
            prompt,
            ["Rewind here (discard newer)", "Branch from here (keep both)", "Cancel"])
        if idx == 0:
            await self._apply_rewind(row)
        elif idx == 1:
            name = await self.ask_text("Name the new branch:",
                                       placeholder="e.g. alt-approach", multiline=False)
            if name and name.strip():
                await self._branch_from(row, name.strip())

    def _rewind_crosses_baseline(self, rows: list[dict], target_id: str) -> bool:
        """True if a 'baseline' row (a resume point capturing external edits) sits AFTER
        the target in the timeline — rewinding past it discards out-of-session changes."""
        seen = False
        for r in rows:
            if r["checkpoint_id"] == target_id:
                seen = True
                continue
            if seen and r.get("kind") == "baseline":
                return True
        return False

    def _completed_turns(self, msgs: list) -> int:
        """How many receipts to keep after a truncation: one per COMPLETED turn. A
        thread ending on a human turn or an unanswered tool batch has an open last turn."""
        humans = sum(1 for m in msgs if isinstance(m, HumanMessage))
        if not msgs:
            return 0
        last = msgs[-1]
        incomplete = (isinstance(last, (HumanMessage, ToolMessage))
                      or (isinstance(last, AIMessage) and last.tool_calls))
        return max(0, humans - (1 if incomplete else 0))

    async def _apply_rewind(self, row: dict) -> None:
        """Restore files to `row`'s checkpoint, truncate this branch's thread + receipts
        + timeline to it, move the tip, replay, and drop a marker."""
        repo = self._ensure_checkpoints()
        commit = store.registry_commit(self._project_id, self._conv_id, row["checkpoint_id"])
        if repo is not None and commit:
            try:
                repo.restore(commit)
            except CheckpointError as e:
                self.notify(f"could not restore files: {e}", severity="error")
                return
        idx = row["message_index"]
        self._history = self._history[:idx]
        store.write_branch_thread(self._project_id, self._conv_id, self._cp_branch, self._history)
        self._persisted_count = len(self._history)
        store.truncate_branch_receipts(self._project_id, self._conv_id, self._cp_branch,
                                       self._completed_turns(self._history))
        store.write_timeline(self._project_id, self._conv_id, self._cp_branch,
                             _truncate_to(self._timeline(), row["checkpoint_id"]))
        # Abandoned commits stay reachable via their per-checkpoint refs → recoverable.
        self._cp_tip_id = row["checkpoint_id"]
        self._cp_tip_sha = commit
        try:
            store.write_branch_meta(self._project_id, self._conv_id, self._cp_branch,
                                    tip=row["checkpoint_id"])
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=self._cp_branch, msg_count=len(self._history))
            if repo is not None and commit:
                repo.ref_set(self._branch_ref(self._cp_branch), commit)
        except (CheckpointError, OSError):
            pass
        await self._replay_history(self._history)
        await self._drop_marker(
            f"rewound to “{row['label'] or 'start'}” — files and conversation restored")

    async def _drop_marker(self, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(SystemNote(text, kind="branch"))
        log.scroll_end(animate=False)

    # ── branch / switch (Plan E) ──────────────────────────────────────────────
    def _branch_entries(self) -> list[dict]:
        """One row per branch: name, its tip's label, when, and whether it's active."""
        entries: list[dict] = []
        for name in store.list_branches(self._project_id, self._conv_id):
            rows = store.read_timeline(self._project_id, self._conv_id, name)
            tip = rows[-1] if rows else {}
            entries.append({"name": name, "current": name == self._cp_branch,
                            "label": tip.get("label", ""),
                            "when": _relative_iso(tip.get("created"))})
        entries.sort(key=lambda e: (not e["current"], e["name"]))
        return entries

    def action_open_branches(self) -> None:
        self.run_worker(self._branch_flow())

    async def _branch_flow(self) -> None:
        """`/branch` — switch branches, or fork a new one from a checkpoint."""
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        if not self._timeline():
            self.notify("No checkpoints yet — they're saved automatically as you work.", severity="warning")
            return
        choice = await self.push_screen_wait(BranchScreen(self._branch_entries()))
        if not choice:
            return
        if choice == NEW_BRANCH:
            await self._new_branch_flow()
        elif choice != self._cp_branch:
            await self._switch_branch(choice)

    async def _new_branch_flow(self) -> None:
        """Pick a checkpoint, name it, fork."""
        rows = self._timeline()
        cid = await self.push_screen_wait(RewindScreen(self._picker_entries(rows, with_files=False)))
        if not cid:
            return
        row = next((r for r in rows if r["checkpoint_id"] == cid), None)
        if row is None:
            return
        name = await self.ask_text("Name the new branch:",
                                   placeholder="e.g. alt-approach", multiline=False)
        if name and name.strip():
            await self._branch_from(row, name.strip())

    async def _branch_from(self, row: dict, name: str) -> None:
        """Fork a new branch at `row`'s checkpoint: deep-copy the current branch folder,
        truncate the COPY to the checkpoint, restore code, switch. The source branch is
        untouched (both timelines kept); `forked_from` is provenance only."""
        name = store._safe_branch(name)
        if name in store.list_branches(self._project_id, self._conv_id):
            self.notify(f"branch '{name}' already exists", severity="warning")
            return
        repo = self._ensure_checkpoints()
        commit = store.registry_commit(self._project_id, self._conv_id, row["checkpoint_id"])
        if repo is not None and commit:
            try:
                repo.restore(commit)
            except CheckpointError as e:
                self.notify(f"could not restore files: {e}", severity="error")
                return
        src = self._cp_branch
        try:
            store.copy_branch(self._project_id, self._conv_id, src, name)
        except OSError as e:
            self.notify(f"could not create branch: {e}", severity="error")
            return
        idx = row["message_index"]
        new_thread = self._history[:idx]
        store.write_branch_thread(self._project_id, self._conv_id, name, new_thread)
        store.truncate_branch_receipts(self._project_id, self._conv_id, name,
                                       self._completed_turns(new_thread))
        store.write_timeline(self._project_id, self._conv_id, name,
                             _truncate_to(store.read_timeline(self._project_id, self._conv_id, name),
                                          row["checkpoint_id"]))
        store.write_branch_meta(self._project_id, self._conv_id, name,
                                tip=row["checkpoint_id"],
                                forked_from={"branch": src, "checkpoint_id": row["checkpoint_id"]})
        self._cp_branch = name
        self._cp_tip_id = row["checkpoint_id"]
        self._cp_tip_sha = commit
        self._history = new_thread
        self._persisted_count = len(new_thread)
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=name, msg_count=len(new_thread))
            if repo is not None and commit:
                repo.ref_set(self._branch_ref(name), commit)
        except (CheckpointError, OSError):
            pass
        await self._replay_history(new_thread)
        await self._drop_marker(f"branched to “{name}” from “{row['label'] or 'start'}” "
                                f"— both timelines kept")

    async def _switch_branch(self, name: str) -> None:
        """Switch the active timeline to `name`: load its thread (already self-contained
        on disk) and restore the code to its tip. No copying — the live turn path writes
        directly into each branch's folder, so nothing needs saving here."""
        bm = store.read_branch_meta(self._project_id, self._conv_id, name)
        tip = bm.get("tip")
        commit = store.registry_commit(self._project_id, self._conv_id, tip) if tip else None
        if commit is None:
            self.notify(f"branch '{name}' has no checkpoint", severity="warning")
            return
        repo = self._ensure_checkpoints()
        self._cp_branch = name
        self._history = store.load_branch_thread(self._project_id, self._conv_id, name)
        self._persisted_count = len(self._history)
        self._cp_tip_id = tip
        self._cp_tip_sha = commit
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=name, msg_count=len(self._history))
        except OSError:
            pass
        if repo is not None:
            try:
                repo.restore(commit)
            except CheckpointError:
                pass
        await self._replay_history(self._history)
        await self._drop_marker(f"switched to branch “{name}”")

    # ── fork to a worktree (Plan F) ───────────────────────────────────────────
    def action_open_fork(self) -> None:
        self.run_worker(self._fork_flow())

    async def _fork_flow(self) -> None:
        """`/fork` — materialize a checkpoint's code in a NEW directory (git worktree)
        and seed a conversation there, for a parallel timeline in its own dir."""
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        repo = self._ensure_checkpoints()
        if repo is None:
            self.notify("fork needs git (checkpoints unavailable)", severity="warning")
            return
        rows = self._timeline()
        if not rows:
            self.notify("No checkpoints yet — they're saved automatically as you work.", severity="warning")
            return
        cid = await self.push_screen_wait(RewindScreen(self._picker_entries(rows, with_files=False)))
        if not cid:
            return
        row = next((r for r in rows if r["checkpoint_id"] == cid), None)
        if row is None:
            return
        default = str(Path(self._cwd).resolve().parent / f"{Path(self._cwd).name}-fork")
        path = await self.ask_text("Fork into which directory? (must not exist yet)",
                                   placeholder=default, multiline=False)
        path = os.path.abspath(os.path.expanduser((path or "").strip() or default))
        fork_cid = self._do_fork(row, path)
        if fork_cid is None:
            return
        short = path.replace(os.path.expanduser("~"), "~")
        await self._drop_marker(
            f"forked to {short} at “{row['label'] or 'start'}” — "
            f"run `cd {short} && visvoai --resume {fork_cid}`")

    def _do_fork(self, row: dict, path: str) -> str | None:
        """Create a detached worktree at `path` for `row`'s commit and seed an
        independent conversation (truncated thread + receipts) inside it. Returns the
        new conversation id, or None on failure (already surfaced)."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return None
        commit = store.registry_commit(self._project_id, self._conv_id, row["checkpoint_id"])
        if not commit:
            self.notify("checkpoint has no commit", severity="error")
            return None
        try:
            repo.add_worktree(path, commit)
        except CheckpointError as e:
            self.notify(f"could not create worktree: {e}", severity="error")
            return None
        try:
            fork_pid = store.resolve_project_id(path)
            fork_cid = store.new_conversation_id()
            thread = self._history[:row["message_index"]]
            receipts = store.read_branch_receipts(self._project_id, self._conv_id, self._cp_branch)
            store.seed_conversation(
                fork_pid, fork_cid, thread, receipts[:self._completed_turns(thread)],
                title=store.read_meta(self._project_id, self._conv_id).get("title"),
                model=self._model)
        except OSError as e:
            self.notify(f"forked files but could not seed conversation: {e}",
                        severity="warning")
            return None
        return fork_cid

    # ── export (Plan G) ───────────────────────────────────────────────────────
    def _render_transcript(self) -> str:
        """The active thread as a readable markdown transcript (a 'gist')."""
        meta = store.read_meta(self._project_id, self._conv_id)
        title = meta.get("title") or store.title_for(self._history) or "conversation"
        lines = [f"# {title}", ""]
        for m in self._history:
            kind = m.__class__.__name__
            if kind == "HumanMessage":
                lines += ["## You", "", agent.chunk_text(m).strip(), ""]
            elif kind == "AIMessage":
                text = agent.chunk_text(m).strip()
                if text:
                    lines += ["## Assistant", "", text, ""]
                for tc in (getattr(m, "tool_calls", None) or []):
                    lines += [f"> 🔧 `{tc.get('name', 'tool')}({agent.fmt_args(tc.get('args') or {})})`", ""]
        return "\n".join(lines).rstrip() + "\n"

    def action_open_export(self) -> None:
        self.run_worker(self._export_flow())

    async def _export_flow(self) -> None:
        """`/export` — write a shareable artifact: a markdown transcript, or a full
        bundle (transcript + thread + a git bundle of the branch's code)."""
        if self._project_id is None or self._conv_id is None or not self._history:
            self.notify("Nothing to export yet — start a conversation first.", severity="warning")
            return
        idx, _ = await self.ask_choice(
            "Export this conversation as:",
            ["Transcript (.md)", "Full bundle (transcript + code)"])
        if idx is None:
            return
        meta = store.read_meta(self._project_id, self._conv_id)
        slug = store._safe_branch(meta.get("title") or store.title_for(self._history) or "conversation")[:40]
        if idx == 0:
            default = str(Path(self._cwd) / f"{slug}.md")
            out = os.path.abspath(os.path.expanduser(
                (await self.ask_text("Write transcript to:", placeholder=default,
                                     multiline=False) or "").strip() or default))
            path = self._do_export("transcript", out)
        else:
            default = str(Path(self._cwd) / f"{slug}.visvoexport")
            out = os.path.abspath(os.path.expanduser(
                (await self.ask_text("Write bundle into directory:", placeholder=default,
                                     multiline=False) or "").strip() or default))
            path = self._do_export("bundle", out)
        if path:
            await self._drop_marker(f"exported → {path.replace(os.path.expanduser('~'), '~')}")

    def _do_export(self, kind: str, out_path: str) -> str | None:
        """`transcript` → a .md file. `bundle` → a dir with transcript.md, thread.jsonl,
        manifest.json, and code.bundle (a git bundle of the active branch's history)."""
        try:
            if kind == "transcript":
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_text(self._render_transcript(), encoding="utf-8")
                return out_path
            d = Path(out_path)
            d.mkdir(parents=True, exist_ok=True)
            (d / "transcript.md").write_text(self._render_transcript(), encoding="utf-8")
            store.write_thread_to(d / "thread.jsonl", self._history)
            has_code = False
            repo = self._ensure_checkpoints()
            if repo is not None:
                ref = self._branch_ref(self._cp_branch)
                if repo.ref_get(ref):
                    try:
                        repo.bundle(str(d / "code.bundle"), [ref])
                        has_code = True
                    except CheckpointError:
                        has_code = False
            import json
            (d / "manifest.json").write_text(json.dumps({
                "branch": self._cp_branch, "messages": len(self._history),
                "code_bundle": has_code, "tip": self._cp_tip_sha,
            }, indent=2), encoding="utf-8")
            return out_path
        except OSError as e:
            self.notify(f"export failed: {e}", severity="error")
            return None

    # ── log (Plan E) ──────────────────────────────────────────────────────────
    async def _log_flow(self) -> None:
        """`/log` — print the active branch's timeline (newest first), tip marked."""
        from visvoai.cli.widgets import Welcome
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        rows = self._timeline()
        if not rows:
            self.notify("No checkpoints yet — they're saved automatically as you work.", severity="warning")
            return
        primary, muted = self._tv("primary"), self._tv("muted")
        tags = {"turn": "turn end", "pre_batch": "before tools", "baseline": "start"}
        out = []
        for r in reversed(rows):
            mark = "●" if r["checkpoint_id"] == self._cp_tip_id else "│"
            tag = tags.get(r["kind"], r["kind"])
            out.append(f"  [{primary}]{mark}[/] {r['label'] or '(start)'}   "
                       f"[dim {muted}]{tag} · {_relative_iso(r.get('created'))}[/]")
        markup = (f"[b {primary}]branch {self._cp_branch}[/]  "
                  f"[dim {muted}]({len(rows)} checkpoints)[/]\n\n" + "\n".join(out))
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Welcome(lambda: markup))
        log.scroll_end(animate=False)
