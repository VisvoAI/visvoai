"""
sessions.py — SessionsMixin: conversation persistence-resume + the sessions/git
full-screen pickers.

/resume (and --resume at launch) list this project's saved conversations and
replay the chosen thread; /commit opens the git view. Mixed into VisvoApp; calls
shared primitives (_begin_turn/_mount_block) via self.
"""
from __future__ import annotations

from textual.containers import VerticalScroll

from visvoai.cli import agent, gitio, store
from visvoai.cli.screens import GitScreen, SessionsScreen
from visvoai.cli.widgets import SystemNote


def _footer_text(receipt: dict) -> str:
    """Turn-receipt line from a saved receipt — same shape as the live footer."""
    parts = [f"{receipt.get('seconds', 0):.1f}s",
             receipt.get("model_name") or receipt.get("model", "")]
    level = receipt.get("thinking_level")
    if level:
        parts.append(f"Thinking Level: {str(level).title()}")
    tin, tout = receipt.get("input_tokens", 0), receipt.get("output_tokens", 0)
    if tin or tout:
        parts.append(f"{tin + tout:,} tok")
        parts.append(f"~${receipt.get('cost', 0):.4f}")
    return " · ".join(p for p in parts if p)


class SessionsMixin:
    """Persistence-resume + the sessions and git full-screen views."""


    async def _startup_resume_flow(self) -> None:
        """`--resume <id>` / `--resume` (latest): load + replay a saved conversation
        at launch. Missing id or empty store → a notice, then a fresh session."""
        self._project_id = store.resolve_project_id(self._cwd)
        convs = store.list_conversations(self._project_id)
        target = self._startup_resume
        if target == "__last__":
            if not convs:
                self.notify("no past conversations to resume — starting fresh")
                return
            conv_id = convs[0]["id"]
        elif any(c["id"] == target for c in convs):
            conv_id = target
        else:
            self.notify(f"conversation '{target}' not found — starting fresh")
            return
        try:
            messages = store.load_conversation(self._project_id, conv_id)
        except Exception as e:
            self.notify(f"could not load '{conv_id}': {e}")
            return
        self._history = list(messages)
        self._persisted_count = len(messages)   # all loaded msgs are already on disk
        self._title_generated = True            # existing thread already has its title
        self._conv_id = conv_id
        await self._replay_history(messages)
        self._resume_checkpoints()   # adopt the checkpoint tip; baseline any external drift
        meta = store.read_meta(self._project_id, conv_id)
        self.set_tab_title(meta.get("title") or store.title_for(messages))
        self.notify(f"resumed: {conv_id}")

    def action_open_sessions(self) -> None:
        self.run_worker(self._open_sessions())

    async def _open_sessions(self) -> None:
        """`/resume` (Ctrl+R) — list this project's saved conversations; on select,
        load the thread and replay it into the log so the turn continues it."""
        if self._project_id is None:
            self._project_id = store.resolve_project_id(self._cwd)
        sessions = store.list_conversations(self._project_id)
        sid = await self.push_screen_wait(SessionsScreen(sessions))
        if not sid:
            return
        try:
            messages = store.load_conversation(self._project_id, sid)
        except Exception as e:
            self.notify(f"could not load conversation: {e}")
            return
        self._history = list(messages)
        self._persisted_count = len(messages)   # all loaded msgs are already on disk
        self._title_generated = True            # existing thread already has its title
        self._conv_id = sid
        await self._replay_history(messages)
        self._resume_checkpoints()   # adopt the checkpoint tip; baseline any external drift
        self.set_tab_title(store.read_meta(self._project_id, sid).get("title")
                           or store.title_for(messages))
        title = next((s["title"] for s in sessions if s["id"] == sid), sid)
        self.notify(f"resumed: {title}")

    async def _replay_history(self, messages: list) -> None:
        """Rebuild the FULL turn trace from saved history: user anchors, reasoning
        (collapsed Thinking, with saved duration), tool calls + results, answers, and
        the per-turn receipt footer (duration · model · tokens · cost). Message content
        comes from history; the durations/cost/footer come from the receipts sidecar
        (UI metadata, never in model context)."""
        from visvoai.cli.widgets import Thinking, TurnFooter

        log = self.query_one("#log", VerticalScroll)
        await log.remove_children()
        self._turns = 0
        receipts = store.read_receipts(self._project_id, self._conv_id) if self._conv_id else []
        turn_idx = -1                 # advances on each HumanMessage
        think_i = 0                   # index into the current turn's thinking_durations
        pending: dict = {}            # tool_call_id → (name, args), paired with its ToolMessage

        async def _flush_footer() -> None:
            """Render the just-finished turn's receipt footer (if we have one)."""
            if 0 <= turn_idx < len(receipts):
                await log.mount(TurnFooter(_footer_text(receipts[turn_idx])))

        for m in messages:
            kind = m.__class__.__name__
            if kind == "HumanMessage":
                await _flush_footer()           # close the previous turn
                turn_idx += 1
                think_i = 0
                await self._begin_turn(log, agent.chunk_text(m))
            elif kind == "AIMessage":
                reasoning = agent.thinking_text(m)
                if reasoning.strip():
                    durations = (receipts[turn_idx]["thinking_durations"]
                                 if 0 <= turn_idx < len(receipts) else [])
                    elapsed = durations[think_i] if think_i < len(durations) else None
                    think_i += 1
                    t = Thinking()
                    await self._mount_block(log, t, "think")
                    t.restore(reasoning, elapsed)
                text = agent.chunk_text(m)
                if text.strip():
                    await self._mount_answer(log, text)
                for tc in (getattr(m, "tool_calls", None) or []):
                    pending[tc.get("id")] = (tc.get("name", "tool"), tc.get("args") or {})
            elif kind == "ToolMessage":
                name, args = pending.pop(getattr(m, "tool_call_id", None), ("tool", {}))
                node = await self._tool_node(log, name, agent.fmt_args(args))
                await self._render_tool_result(
                    node, name, args, agent.tool_output_text(m))
        await _flush_footer()                   # close the final turn
        self._restore_cost_and_context(receipts)
        log.scroll_end(animate=False)

    def _restore_cost_and_context(self, receipts: list) -> None:
        """Sum the conversation cost from receipts and restore the context gauge from
        the most recent turn — so the footer reflects the resumed session."""
        self._conv_cost = sum(r.get("cost", 0.0) for r in receipts)
        self._update_cost_status()
        # Restore the gauge from the most recent receipt that actually reported a
        # token count — a final errored/usage-less turn (context_tokens=0) must not
        # blank or freeze the gauge when earlier turns have real context.
        for r in reversed(receipts):
            ct = r.get("context_tokens") or 0
            if not ct:
                continue
            dv = agent.deployment_view(r.get("model") or self._model)
            if dv and dv.context_window:
                self._set_context(round(ct / dv.context_window * 100), ct)
            break

    def action_open_git(self) -> None:
        self.run_worker(self._open_git())

    async def _open_git(self) -> None:
        """`/commit` (Ctrl+G) — read the real working tree, push the full-screen git
        view (stage with ctrl+s, commit with enter); on commit, drop a marker note.
        The CLI never auto-commits — this is the explicit gate."""
        status = gitio.working_tree_status(self._cwd)
        if not status:
            self.notify("nothing to commit — working tree clean (or not a git repo)")
            return
        result = await self.push_screen_wait(GitScreen(status, cwd=self._cwd))
        if result:
            log = self.query_one("#log", VerticalScroll)
            await log.mount(SystemNote(
                f'committed {result["n_files"]} file(s) on {result["branch"]} '
                f'— "{result["message"]}"',
                kind="branch",
            ))
            log.scroll_end(animate=False)
