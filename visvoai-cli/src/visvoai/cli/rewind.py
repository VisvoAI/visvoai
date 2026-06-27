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
        prompt = f"Go back to “{cp['label'] or 'start'}”?"
        if warn:
            prompt += " ⚠ Rewinding past here also discards changes made outside this session."
        idx, _ = await self.ask_choice(
            prompt,
            ["Rewind here (discard newer)", "Branch from here (keep both)", "Cancel"])
        if idx == 0:
            await self._apply_rewind(cp)
        elif idx == 1:
            name = await self.ask_text("Name the new branch:",
                                       placeholder="e.g. alt-approach", multiline=False)
            if name and name.strip():
                await self._branch_from(cp, name.strip())

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
        await self._drop_marker(
            f"rewound to “{cp['label'] or 'start'}” — files and conversation restored")

    async def _drop_marker(self, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(SystemNote(text, kind="branch"))
        log.scroll_end(animate=False)

    # ── branch / switch (Plan E) ──────────────────────────────────────────────
    def _branch_entries(self, records: list[dict]) -> list[dict]:
        """One row per known branch: name, its tip's label, when, and whether it's
        active. Tips come from meta (branch_tips), labels from the checkpoint records."""
        by_id = {r["id"]: r for r in records}
        entries: list[dict] = []
        for name, tip_id in self._cp_branch_tips.items():
            tip = by_id.get(tip_id)
            entries.append({
                "name": name,
                "current": name == self._cp_branch,
                "label": (tip or {}).get("label", ""),
                "when": _relative_iso((tip or {}).get("created")),
            })
        # Active branch first, then the rest alphabetically — stable + predictable.
        entries.sort(key=lambda e: (not e["current"], e["name"]))
        return entries

    def action_open_branches(self) -> None:
        self.run_worker(self._branch_flow())

    async def _branch_flow(self) -> None:
        """`/branch` — switch branches, or fork a new one from a checkpoint."""
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        records = store.read_checkpoints(self._project_id, self._conv_id)
        if not records:
            self.notify("no checkpoints yet — run a turn first", severity="warning")
            return
        if self._cp_tip_id is None:
            self._load_checkpoint_tip(records)
        self._cp_branch_tips.setdefault(self._cp_branch, self._cp_tip_id)
        choice = await self.push_screen_wait(BranchScreen(self._branch_entries(records)))
        if not choice:
            return
        if choice == NEW_BRANCH:
            await self._new_branch_flow(records)
        elif choice != self._cp_branch:
            await self._switch_branch(choice)

    async def _new_branch_flow(self, records: list[dict]) -> None:
        """Pick a checkpoint, name it, fork."""
        chain = self._active_chain(records)
        entries = [{**cp, "files": None, "when": _relative_iso(cp.get("created"))}
                   for cp in reversed(chain)]
        cid = await self.push_screen_wait(RewindScreen(entries))
        if not cid:
            return
        cp = next((c for c in records if c["id"] == cid), None)
        if cp is None:
            return
        name = await self.ask_text("Name the new branch:",
                                   placeholder="e.g. alt-approach", multiline=False)
        if name and name.strip():
            await self._branch_from(cp, name.strip())

    async def _branch_from(self, cp: dict, name: str) -> None:
        """Fork a new branch starting at `cp`: preserve the current branch's thread,
        restore the code to `cp`, and make the new branch active with the thread
        truncated to `cp`. Both timelines are kept (non-destructive rewind)."""
        name = store._safe_branch(name)
        if name in self._cp_branch_tips:
            self.notify(f"branch '{name}' already exists", severity="warning")
            return
        repo = self._ensure_checkpoints()
        # Preserve the branch we're leaving (thread + receipts).
        store.save_branch_thread(self._project_id, self._conv_id, self._cp_branch, self._history)
        store.save_branch_receipts(self._project_id, self._conv_id, self._cp_branch,
                                   store.read_receipts(self._project_id, self._conv_id))
        if repo is not None:
            try:
                repo.restore(cp["commit"])
            except CheckpointError as e:
                self.notify(f"could not restore files: {e}", severity="error")
                return
        new_thread = self._history[:cp["message_index"]]
        self._history = new_thread
        self._cp_branch = name
        self._cp_tip_id = cp["id"]
        self._cp_tip_sha = cp["commit"]
        self._cp_branch_tips[name] = cp["id"]
        store.save_conversation(self._project_id, self._conv_id, new_thread)
        store.save_branch_thread(self._project_id, self._conv_id, name, new_thread)
        self._persisted_count = len(new_thread)
        store.truncate_receipts(self._project_id, self._conv_id, self._completed_turns(new_thread))
        store.save_branch_receipts(self._project_id, self._conv_id, name,
                                   store.read_receipts(self._project_id, self._conv_id))
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=name, branch_tips=self._cp_branch_tips)
            if repo is not None:
                repo.ref_set(f"refs/visvoai/{self._conv_id}/{name}", cp["commit"])
        except (CheckpointError, OSError):
            pass
        await self._replay_history(new_thread)
        await self._drop_marker(f"branched to “{name}” from “{cp['label'] or 'start'}” "
                                f"— both timelines kept")

    async def _switch_branch(self, name: str) -> None:
        """Switch the active timeline to `name`: persist the current branch, load the
        target's thread + receipts, and restore the code to its tip."""
        records = store.read_checkpoints(self._project_id, self._conv_id)
        tip_id = self._cp_branch_tips.get(name)
        tip = next((r for r in records if r["id"] == tip_id), None)
        if tip is None:
            self.notify(f"branch '{name}' has no checkpoint", severity="warning")
            return
        repo = self._ensure_checkpoints()
        # Preserve the branch we're leaving.
        store.save_branch_thread(self._project_id, self._conv_id, self._cp_branch, self._history)
        store.save_branch_receipts(self._project_id, self._conv_id, self._cp_branch,
                                   store.read_receipts(self._project_id, self._conv_id))
        # Adopt the target.
        msgs = store.load_branch_thread(self._project_id, self._conv_id, name)
        self._history = list(msgs)
        store.save_conversation(self._project_id, self._conv_id, msgs)
        self._persisted_count = len(msgs)
        store.write_receipts(self._project_id, self._conv_id,
                             store.load_branch_receipts(self._project_id, self._conv_id, name))
        self._cp_branch = name
        self._cp_tip_id = tip["id"]
        self._cp_tip_sha = tip["commit"]
        try:
            store.write_meta(self._project_id, self._conv_id,
                             active_branch=name, branch_tips=self._cp_branch_tips)
        except OSError:
            pass
        if repo is not None:
            try:
                repo.restore(tip["commit"])
            except CheckpointError:
                pass
        await self._replay_history(msgs)
        await self._drop_marker(f"switched to branch “{name}”")

    # ── fork (Plan F) ─────────────────────────────────────────────────────────
    def action_open_fork(self) -> None:
        self.run_worker(self._fork_flow())

    async def _fork_flow(self) -> None:
        """`/fork` — materialize a checkpoint's code in a NEW directory (git worktree)
        and seed a conversation there, so you can run a second timeline in parallel
        without disturbing this one."""
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        repo = self._ensure_checkpoints()
        if repo is None:
            self.notify("fork needs git (checkpoints unavailable)", severity="warning")
            return
        records = store.read_checkpoints(self._project_id, self._conv_id)
        if not records:
            self.notify("no checkpoints yet — run a turn first", severity="warning")
            return
        if self._cp_tip_id is None:
            self._load_checkpoint_tip(records)
        chain = self._active_chain(records)
        entries = [{**cp, "files": None, "when": _relative_iso(cp.get("created"))}
                   for cp in reversed(chain)]
        cid = await self.push_screen_wait(RewindScreen(entries))
        if not cid:
            return
        cp = next((c for c in records if c["id"] == cid), None)
        if cp is None:
            return
        default = str(Path(self._cwd).resolve().parent / f"{Path(self._cwd).name}-fork")
        path = await self.ask_text("Fork into which directory? (must not exist yet)",
                                   placeholder=default, multiline=False)
        path = os.path.abspath(os.path.expanduser((path or "").strip() or default))
        fork_cid = self._do_fork(cp, path)
        short = path.replace(os.path.expanduser("~"), "~")
        if fork_cid is None:
            return   # _do_fork already surfaced the failure
        await self._drop_marker(
            f"forked to {short} at “{cp['label'] or 'start'}” — "
            f"run `cd {short} && visvoai --resume {fork_cid}`")

    def _do_fork(self, cp: dict, path: str) -> str | None:
        """Create a detached worktree at `path` for `cp`'s commit and seed an
        independent conversation (truncated thread + receipts + meta) inside it.
        Returns the new conversation id, or None on failure (already surfaced)."""
        repo = self._ensure_checkpoints()
        if repo is None:
            return None
        try:
            repo.add_worktree(path, cp["commit"])
        except CheckpointError as e:
            self.notify(f"could not create worktree: {e}", severity="error")
            return None
        try:
            fork_pid = store.resolve_project_id(path)
            fork_cid = store.new_conversation_id()
            thread = self._history[:cp["message_index"]]
            store.save_conversation(fork_pid, fork_cid, thread)
            store.write_receipts(fork_pid, fork_cid,
                                 store.read_receipts(self._project_id, self._conv_id)
                                 [:self._completed_turns(thread)])
            src_meta = store.read_meta(self._project_id, self._conv_id)
            store.write_meta(fork_pid, fork_cid,
                             title=(src_meta.get("title") or store.title_for(thread)),
                             model=self._model, msg_count=len(thread))
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
        """`/export` — write this conversation as a shareable artifact: a markdown
        transcript, or a full bundle (transcript + thread + a git bundle of the code)."""
        if self._project_id is None or self._conv_id is None or not self._history:
            self.notify("nothing to export yet", severity="warning")
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
        """Write the export. `transcript` → a single .md file. `bundle` → a directory
        with transcript.md, thread.jsonl, manifest.json, and code.bundle (a git bundle
        of the active branch's checkpoints). Returns the path written, or None."""
        try:
            if kind == "transcript":
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_text(self._render_transcript(), encoding="utf-8")
                return out_path
            # bundle: a self-contained directory
            d = Path(out_path)
            d.mkdir(parents=True, exist_ok=True)
            (d / "transcript.md").write_text(self._render_transcript(), encoding="utf-8")
            store.save_conversation_to(d / "thread.jsonl", self._history)
            has_code = False
            repo = self._ensure_checkpoints()
            if repo is not None:
                ref = f"refs/visvoai/{self._conv_id}/{self._cp_branch}"
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
        """`/log` — print the active branch's checkpoint chain (newest first) into the
        conversation, the current point marked."""
        from visvoai.cli.widgets import Welcome
        if self._project_id is None or self._conv_id is None:
            self.notify("no conversation yet", severity="warning")
            return
        records = store.read_checkpoints(self._project_id, self._conv_id)
        if not records:
            self.notify("no checkpoints yet — run a turn first", severity="warning")
            return
        if self._cp_tip_id is None:
            self._load_checkpoint_tip(records)
        chain = self._active_chain(records)
        primary, muted = self._tv("primary"), self._tv("muted")
        tags = {"turn": "turn end", "pre_batch": "before tools", "baseline": "start"}
        rows = []
        for cp in reversed(chain):
            mark = "●" if cp["id"] == self._cp_tip_id else "│"
            tag = tags.get(cp["kind"], cp["kind"])
            rows.append(f"  [{primary}]{mark}[/] {cp['label'] or '(start)'}   "
                        f"[dim {muted}]{tag} · {_relative_iso(cp.get('created'))}[/]")
        markup = (f"[b {primary}]branch {self._cp_branch}[/]  "
                  f"[dim {muted}]({len(chain)} checkpoints)[/]\n\n" + "\n".join(rows))
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Welcome(lambda: markup))
        log.scroll_end(animate=False)
