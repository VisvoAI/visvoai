"""
agent_turn.py — AgentTurnMixin: the real agent turn driven by visvoai-core.

Owns the live turn: input submit/interrupt → _run_real_turn (astream_events
mapped onto the Style-B widgets) → per-tool rendering (_render_tool_result),
the permission gate (_approve), and persistence (_persist_turn). Mixed into
VisvoApp; shared turn primitives (_begin_turn/_mount_block/_tool_node) and HITL
prompts (ask_choice) live on VisvoApp and are called via self.
"""
from __future__ import annotations

import asyncio
import re

from textual.containers import VerticalScroll

import time

from visvoai.cli import agent, store
from visvoai.cli import state as ui_state   # aliased: `state` is a local (graph input) below
from visvoai.cli.widgets import (
    Assistant, CleanDiff, ErrorBlock, Plan, SystemNote, Thinking, ToolOutput,
    TurnFooter, WorkingIndicator, adaptive_tips,
)
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from visvoai.cli.widgets.prompt import PromptArea


def _sanitize_thread(msgs: list[BaseMessage]) -> list[BaseMessage]:
    """Return a provider-replayable copy of `msgs`: every AIMessage tool_call must be
    answered by a ToolMessage and every ToolMessage must have a producing tool_call.

    The durable store is an append-only log that a crashed/errored turn can leave with
    a dangling tool_call (its result never arrived). We never rewrite that log; instead
    we clean the thread here, at the point it's sent to the model. An AIMessage with
    unanswered tool_calls keeps its text (if any) but loses the tool_calls; an orphan
    ToolMessage is dropped."""
    answered = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    out: list[BaseMessage] = []
    valid_ids: set = set()
    for m in msgs:
        if isinstance(m, AIMessage) and m.tool_calls:
            if all(tc.get("id") in answered for tc in m.tool_calls):
                out.append(m)
                valid_ids.update(tc.get("id") for tc in m.tool_calls)
            elif isinstance(m.content, str) and m.content.strip():
                out.append(AIMessage(content=m.content))   # keep the text, drop dangling calls
            # else: empty AIMessage with only unanswered tool_calls → drop entirely
        elif isinstance(m, ToolMessage):
            if m.tool_call_id in valid_ids:
                out.append(m)
            # else: orphan tool result (its AIMessage was dropped) → drop
        else:
            out.append(m)
    return out


# Tool-result management: the model API is stateless, so the whole thread (incl. every
# tool result) is re-sent on every call. Old tool results (a file read / grep / shell
# output from earlier subtasks) are usually dead weight once the model has acted on
# them — so when building the model input we keep the most RECENT tool results verbatim
# up to a char budget and elide older large ones to a stub (the model can re-run the
# tool if it still needs them). This bounds the CARRIED-OVER context across turns and
# is model-agnostic. It transforms only the copy sent to the model — the durable
# `_history` keeps full fidelity (rewind/replay/persistence unaffected).
TOOL_RESULT_BUDGET_CHARS = 40_000   # ~10k tokens of recent tool output kept verbatim
MIN_ELIDE_CHARS = 400               # don't bother eliding a small old result


def _prune_tool_results(msgs: list[BaseMessage]) -> tuple[list[BaseMessage], int]:
    """Return `(model_messages, n_elided)`: newest→oldest, keep tool results whole until
    `TOOL_RESULT_BUDGET_CHARS` is filled, then replace older large ones with a short
    stub (keeping their tool_call_id so the AIMessage/ToolMessage pairing stays valid).
    Non-tool messages and small/recent results pass through untouched."""
    elide: set[int] = set()
    kept = 0
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if isinstance(m, ToolMessage) and isinstance(m.content, str):
            if kept >= TOOL_RESULT_BUDGET_CHARS and len(m.content) > MIN_ELIDE_CHARS:
                elide.add(i)
            else:
                kept += len(m.content)
    if not elide:
        return msgs, 0
    out: list[BaseMessage] = []
    for i, m in enumerate(msgs):
        if i in elide:
            label = getattr(m, "name", None) or "tool"
            out.append(ToolMessage(
                content=f"[{len(m.content)} chars of earlier {label} output elided to "
                        f"save context — re-run the tool if you still need it]",
                tool_call_id=m.tool_call_id))
        else:
            out.append(m)
    return out, len(elide)


_AUTH_HINTS = ("401", "403", "unauthorized", "api key", "api_key",
               "user not found", "authentication", "invalid_api_key")
_NET_HINTS = ("connection", "timeout", "timed out", "network", "getaddrinfo",
              "temporarily unavailable", "502", "503", "504")


def _nudge_text(changed: int, had_error: bool, used: set[str]) -> str | None:
    """The post-turn nudge to show (or None). Self-silencing: the changed-files nudge
    stops once the user knows both /rewind and /commit; the failure nudge stops once
    they know /rewind."""
    if changed and not ({"rewind", "commit"} <= used):
        plural = "s" if changed != 1 else ""
        return f"{changed} file{plural} changed  ·  /rewind to undo  ·  /commit to keep"
    if had_error and "rewind" not in used:
        return "that didn't fully work — /rewind goes back to before this turn"
    return None


def _classify_turn_error(e: Exception) -> tuple[str, str, str]:
    """Map a raw turn exception to (ErrorBlock kind, human message, dim detail).
    Keeps the raw text as the detail line; never a traceback."""
    raw = " ".join(str(e).split())
    low = raw.lower()
    detail = raw if len(raw) <= 240 else raw[:237] + "…"
    if any(h in low for h in _AUTH_HINTS):
        return ("model",
                "The provider rejected the API key. Check it with /login "
                "(watch for trailing spaces or quotes).", detail)
    if any(h in low for h in _NET_HINTS):
        return ("network", "Couldn't reach the model provider.", detail)
    return ("model", "The model call failed.", detail)


class AgentTurnMixin:
    """The real agent turn + tool rendering + permission gate + persistence."""

    def on_prompt_area_submitted(self, event: PromptArea.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return  # PromptArea already guards this; belt-and-suspenders
        worker = getattr(self, "_turn_worker", None)
        if worker is not None and worker.is_running:
            # A turn is mid-flight — queue the input as a pending redirect instead
            # of starting a competing turn or silently dropping it. The running
            # turn worker reconciles with it (Case B Turn 6).
            self._pending_redirect = text
            self.run_worker(self._note_queued_redirect(text))
            return
        self._turn_worker = self.run_worker(self._run_real_turn(text), exclusive=True)

    async def _note_queued_redirect(self, text: str) -> None:
        """Acknowledge a redirect queued during a running turn so the user sees it
        was received (the turn worker decides when to act on it)."""
        log = self.query_one("#log", VerticalScroll)
        await self._mount_block(log, SystemNote(f"queued redirect: {text}", kind="info"), "note")

    async def on_prompt_area_interrupt(self, event: PromptArea.Interrupt) -> None:
        """Esc in the prompt → stop a streaming turn (if one is running) and drop a
        muted 'stopped' note. No-op when idle. During a HITL the prompt is hidden,
        so esc never lands here — it cancels the Selection/Form instead."""
        worker = getattr(self, "_turn_worker", None)
        if worker is None or not worker.is_running:
            return
        worker.cancel()
        ui_state.record_used("esc")
        self._turn_worker = None
        self._set_status(None)
        # Freeze any live plan spinner — its interval is independent of the worker.
        for plan in self.query(Plan):
            plan.stop()
        log = self.query_one("#log", VerticalScroll)
        await self._mount_block(log, SystemNote("stopped", kind="stopped"), "note")

    # ── the REAL turn — streams visvoai-core output into the Style-B widgets ───
    async def _run_real_turn(self, user_text: str) -> None:
        """Stream a real agent turn: provider (visvoai-ai) → CLIRuntime graph →
        astream_events, mapped onto the wired widgets. Phase 1 covers reply text +
        read/list tool nodes; mutating tools / gate / thinking land in later phases."""
        from langchain_core.messages import HumanMessage

        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, user_text)
        turn_start = time.monotonic()

        # Fail fast (and never open a real client) when the provider has no key.
        if not agent.api_key_available(self._model):
            await self._mount_block(log, SystemNote(
                f"No API key for '{self._model}'. Set the provider's key "
                f"(e.g. GEMINI_API_KEY) to chat.", kind="error"), "note")
            self._set_status(None)
            return

        # MCP tools: cached discovery (connects only on the first turn of a session,
        # or after /mcp trust / config edits invalidate the cache). Never raises.
        from visvoai.cli.mcp import get_mcp_tools
        _mcp_statuses, mcp_tools = await get_mcp_tools(self._cwd)

        # Snapshot pending-trust agents so the turn's end can surface only the ones
        # THIS turn created (e.g. the model wrote a .visvoai/agents/*.md file).
        from visvoai.cli.agents import untrusted_agents
        try:
            pre_untrusted = {s.name for s in untrusted_agents(self._cwd)}
        except Exception:
            pre_untrusted = set()

        try:
            graph = agent.build_agent_graph(
                self._model, self._cwd, approve=self._approve, level=self._thinking,
                extra_tools=mcp_tools, process_registry=self._processes)
        except Exception as e:  # missing key / integration / unknown model — surface it
            await self._mount_block(log, SystemNote(f"model error: {e}", kind="error"), "note")
            self._set_status(None)
            return

        self._history.append(HumanMessage(content=user_text))
        self._persist_turn()   # crash-durable: the question lands on disk before the model runs
        # cli-git-structure: label this turn's checkpoints + lay the baseline (pristine
        # tree) on the first turn of a fresh conversation, before any tool runs.
        self._cp_turn_label = user_text[:60]
        self._maybe_baseline()
        # Post-turn nudges (#2): compare the tree tip before vs after the turn to tell
        # if files changed, and note whether any tool failed.
        self._turn_had_error = False
        pre_tip = self._cp_tip_sha
        # Sanitize before sending to the model: a prior crashed/errored turn may have
        # left a dangling tool_call in the thread (durable log isn't trimmed) — strip it
        # so the provider never sees an unanswered tool_call.
        model_messages, n_elided = _prune_tool_results(_sanitize_thread(self._history))
        state = {"messages": model_messages}

        current: Assistant | None = None         # active reply block (None between runs)
        answer_blocks: list[Assistant] = []      # every reply block this turn (mermaid scan)
        thinking: Thinking | None = None         # active reasoning block (None when not thinking)
        nodes: dict[str, tuple] = {}             # run_id → (node, tool_name, input_args)
        final_messages = None                    # captured from the graph's on_chain_end
        turn_in = turn_out = 0                    # summed token usage across the turn (cost)
        last_input = 0                           # latest call's input ≈ current context size
        thinking_durations: list[float] = []     # each reasoning block's wall-clock seconds
        self._set_status("responding…")
        # Immediate feedback: a spinner so there's never a dead gap before output.
        # Starts in 'working' phase; tips rotate per phase as the turn progresses
        # (thinking → working → tool → working). The indicator's lifetime is
        # bounded — _clear_working removes it the moment real output arrives.
        self._working = WorkingIndicator(tips=adaptive_tips(ui_state.used_features()))
        await log.mount(self._working)
        log.scroll_end(animate=False)
        try:
            # Explicit recursion_limit: LangGraph defaults to 25 — too thin a margin
            # over the core graph's soft step cap, so a deep turn crashes with
            # GRAPH_RECURSION_LIMIT instead of hitting the clean tool-free finalize.
            # 100 leaves generous headroom.
            async for event in graph.astream_events(
                state, version="v2", config={"recursion_limit": 100}
            ):
                kind = event.get("event", "")
                data = event.get("data", {})

                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    u = agent.usage_of(chunk)     # token usage when the call reports it
                    if u["input"] or u["output"]:
                        turn_in += u["input"]; turn_out += u["output"]
                        if u["input"]:
                            last_input = u["input"]   # newest call's input ≈ context size
                    # Tool-call argument deltas carry no text/thinking — without a
                    # status update the spinner sits silently while the model writes
                    # the call. Surface it as "preparing tool call…" so there's no gap.
                    if getattr(chunk, "tool_call_chunks", None) and current is None:
                        self._set_status("preparing tool call…")
                    for ck, text in agent.classify_chunk(chunk):
                        await self._clear_working()   # first real output → drop spinner
                        if ck == "thinking":
                            current = None  # reasoning interrupts any answer run
                            if thinking is None:
                                thinking = Thinking()
                                await self._mount_block(log, thinking, "think")
                                self._set_status("thinking…")
                            thinking.add(text)
                        else:  # text — the answer; close any open reasoning first
                            if thinking is not None:
                                thinking.done()
                                thinking_durations.append(thinking._elapsed or 0.0)
                                thinking = None
                                self._set_status("responding…")
                            if current is None:
                                current = Assistant()
                                answer_blocks.append(current)
                                await self._mount_block(log, current, "answer")
                            await current.add(text)
                        log.scroll_end(animate=False)

                elif kind == "on_tool_start":
                    await self._clear_working()   # first real output → drop spinner
                    current = None  # a tool ends the current reply run
                    if thinking is not None:   # …and any open reasoning
                        thinking.done()
                        thinking_durations.append(thinking._elapsed or 0.0)
                        thinking = None
                    name = event.get("name", "tool")
                    args = data.get("input") or {}
                    node = await self._tool_node(log, name, agent.fmt_args(args))
                    node.set_status("running")
                    nodes[event.get("run_id")] = (node, name, args)
                    self._set_status(f"running {name}…")

                elif kind == "on_chat_model_end":
                    # Crash-durable: append the completed AIMessage (content + any
                    # tool_calls) to the thread and flush to disk NOW, so a hard crash
                    # mid-turn can't lose it. _persist_turn writes only the new tail.
                    out = data.get("output")
                    if isinstance(out, BaseMessage):
                        # cli-git-structure: the model just decided to call tools — the
                        # tree is quiescent (this batch hasn't run). Snapshot BEFORE
                        # appending the requesting AIMessage, so its message_index
                        # excludes it and a rewind here makes the model re-plan.
                        if isinstance(out, AIMessage) and out.tool_calls:
                            self._record_checkpoint(len(self._history), "pre_batch",
                                                    self._cp_turn_label)
                        self._history.append(out)
                        self._persist_turn()

                elif kind == "on_tool_end":
                    entry = nodes.pop(event.get("run_id"), None)
                    if entry is not None:
                        node, name, args = entry
                        await self._render_tool_result(
                            node, name, args, agent.tool_output_text(data.get("output")))
                        log.scroll_end(animate=False)
                    out = data.get("output")
                    if isinstance(out, ToolMessage):   # pairs with the AIMessage tool_call
                        self._history.append(out)
                        self._persist_turn()

                elif kind == "on_tool_error":
                    # Defensive: a tool that raises (rather than returning an ERROR
                    # string) must still stop its spinner + free the agent to recover,
                    # never leave the node spinning forever.
                    entry = nodes.pop(event.get("run_id"), None)
                    if entry is not None:
                        node, name, args = entry
                        node.set_rail("failed"); self._turn_had_error = True
                        await node.set_failure("", str(data.get("error") or "tool error"))
                        log.scroll_end(animate=False)

                elif kind == "on_chain_end":
                    # Only the ROOT graph's end carries the full thread. Inner nodes
                    # also emit {"messages": [...]} partials (e.g. just the model's
                    # latest, empty-content AIMessage) — capturing those would clobber
                    # the thread and drop the human turn (→ an empty, untitled save).
                    if not event.get("parent_ids"):
                        out = data.get("output")
                        if isinstance(out, dict) and "messages" in out:
                            final_messages = out["messages"]
            if thinking is not None:        # stream ended mid-reasoning → collapse it
                thinking.done()
                thinking_durations.append(thinking._elapsed or 0.0)
                thinking = None
        except asyncio.CancelledError:
            if thinking is not None:
                thinking.stop()             # freeze the spinner on interrupt
            await self._mount_block(log, SystemNote("stopped", kind="stopped"), "note")
            raise
        except Exception as e:  # model/network/key failure — surface it, never crash the turn
            if thinking is not None:
                thinking.stop()
            kind, message, detail = _classify_turn_error(e)
            await self._mount_block(log, ErrorBlock(kind, message, detail), "error")
        finally:
            self._set_status(None)
            await self._clear_working()
            # A turn that created a project agent must SAY it needs approval —
            # deterministically, whether or not the model mentioned it (or errored).
            self._notify_pending_agents(before=pre_untrusted)

        # Each message was already persisted incrementally as it completed (above),
        # so an errored/interrupted/crashed turn keeps its work. On success, reconcile
        # self._history with the graph's authoritative final thread (canonical objects)
        # when it's at least as complete; the persist flushes any remaining delta. A
        # dangling tool_call left by an errored turn is never trimmed from storage —
        # it's stripped at point-of-use (_sanitize_thread, when building model state).
        # Skip the wholesale adopt when we elided tool results this turn: final_messages
        # was built from the PRUNED input, so adopting it would overwrite full old
        # tool-result content in memory with stubs. The incremental appends above already
        # hold every new message at full fidelity, so _history stays complete + durable.
        if (n_elided == 0 and final_messages is not None
                and len(final_messages) >= len(self._history)):
            self._history = list(final_messages)
        self._persist_turn()
        # cli-git-structure: capture the post-turn tree. Dedup makes a no-file-change
        # turn free (same commit as the prior checkpoint); the message_index spans the
        # whole turn so "undo this turn" lands at the previous turn-end checkpoint.
        self._record_checkpoint(len(self._history), "turn", self._cp_turn_label)

        # Replace any answer block carrying a ```mermaid fence with its split
        # segments (text + a prominent diagram card) so no raw fence reads as code.
        for blk in answer_blocks:
            await self._reflow_answer(log, blk)

        # Turn receipt — duration · model · thinking · tokens · turn cost. UI ONLY:
        # the footer widget + the receipts sidecar are never in _history, so none of
        # this enters the model context (models/levels can differ across turns).
        elapsed = time.monotonic() - turn_start
        dv = agent.deployment_view(self._model)
        model_name = dv.display_name if dv else self._model
        cost = agent.turn_cost(self._model, turn_in, turn_out)
        self._conv_cost += cost
        # Context fill: newest call's input ≈ tokens currently in the window.
        if dv and dv.context_window and last_input:
            self._set_context(round(last_input / dv.context_window * 100), last_input)
        self._update_cost_status()

        from visvoai.cli.sessions import _footer_text   # one footer format, live + replay
        receipt = {"seconds": elapsed, "model": self._model, "model_name": model_name,
                   "thinking_level": self._thinking, "input_tokens": turn_in,
                   "output_tokens": turn_out, "cost": cost}
        await log.mount(TurnFooter(_footer_text(receipt)))
        log.scroll_end(animate=False)

        self._persist_receipt(elapsed, model_name, cost, turn_in, turn_out,
                              last_input, thinking_durations)
        await self._maybe_turn_nudges(pre_tip, log)
        self._rotate_placeholder()   # freshen the next prompt's example (#5)

    def _persist_receipt(self, seconds, model_name, cost, tin, tout, context_tokens,
                         thinking_durations):
        """Write the per-turn receipt (UI metadata, not message history) so resume can
        restore the footer + thinking durations + context gauge and sum the cost."""
        if self._project_id is None or self._conv_id is None:
            return
        try:
            store.append_branch_receipt(self._project_id, self._conv_id, self._cp_branch, {
                "seconds": round(seconds, 1), "model": self._model, "model_name": model_name,
                "thinking_level": self._thinking, "thinking_durations": thinking_durations,
                "input_tokens": tin, "output_tokens": tout,
                "context_tokens": context_tokens, "cost": cost,
            })
        except Exception as e:  # persistence must never break the turn
            self.notify(f"could not save receipt: {e}")

    async def _maybe_turn_nudges(self, pre_tip: str | None, log) -> None:
        """After a turn: a contextual nudge (#2) when files changed or a tool failed,
        and a one-time coachmark (#3) the first time a checkpoint is ever taken. Both
        self-silence — the changed-files nudge stops once the user knows /rewind AND
        /commit; the failure nudge stops once they know /rewind. Best-effort/quiet."""
        used = ui_state.used_features()
        repo = getattr(self, "_checkpoints", None)
        changed = 0
        if repo and pre_tip and self._cp_tip_sha and pre_tip != self._cp_tip_sha:
            try:
                changed = len(repo.diff_names(pre_tip, self._cp_tip_sha))
            except Exception:
                changed = 0
        hint = _nudge_text(changed, getattr(self, "_turn_had_error", False), used)
        if hint:
            await self._mount_hint(log, hint)
        # One-time: the first time this user ever gets a checkpoint, explain it once.
        if repo and self._cp_tip_id and ui_state.mark_shown("coach_checkpoint"):
            await self._mount_hint(log, "↩ your work is auto-saved each turn — /rewind "
                                        "(Ctrl+B) restores files + chat to any point, "
                                        "/branch keeps both")

    async def _mount_hint(self, log, text: str) -> None:
        """A quiet, muted one-liner appended below the turn (not part of history)."""
        await log.mount(SystemNote(text, kind="info"))
        log.scroll_end(animate=False)

    async def _clear_working(self) -> None:
        """Remove the transient working spinner once real output begins (idempotent)."""
        w = getattr(self, "_working", None)
        if w is not None:
            w.stop()
            if w.is_mounted:
                await w.remove()
            self._working = None

    def _persist_turn(self) -> None:
        """Save the current thread to the project's global conversation store.
        Resolves project_id + a conversation id lazily on the first save."""
        # Never persist a degenerate thread (no user turn → nothing to title or
        # resume). Guards against a malformed final state slipping through.
        if not any(m.__class__.__name__ == "HumanMessage" for m in self._history):
            return
        try:
            if self._project_id is None:
                self._project_id = store.resolve_project_id(self._cwd)
            if self._conv_id is None:
                self._conv_id = store.new_conversation_id()
                store.ensure_branch(self._project_id, self._conv_id, self._cp_branch)
            # Append only the new tail (everything past what's already on disk) to the
            # ACTIVE branch's thread.
            new = self._history[self._persisted_count:]
            store.append_branch_messages(self._project_id, self._conv_id, self._cp_branch, new)
            self._persisted_count = len(self._history)
            # Conversation meta: model + count + active branch + a fallback title (the
            # first prompt) only until the LLM title lands — never overwrite that.
            meta = store.read_meta(self._project_id, self._conv_id)
            fields = {"model": self._model, "thinking": self._thinking,
                      "msg_count": len(self._history),
                      "active_branch": self._cp_branch}
            if not meta.get("title"):
                fields["title"] = store.title_for(self._history)
            store.write_meta(self._project_id, self._conv_id, **fields)
            # Reflect the conversation in the terminal tab: 'VisvoAI | <title>'.
            self.set_tab_title(meta.get("title") or fields.get("title"))
            # Refine the title once, in the background, after the first exchange.
            if not self._title_generated:
                self._title_generated = True
                self.run_worker(self._refine_title_async())
        except Exception as e:  # persistence must never break the turn
            self.notify(f"could not save conversation: {e}")

    async def _refine_title_async(self) -> None:
        """Background one-shot: summarize the opening turn into a better title, save
        it to meta, and update the tab. No-op if the model call yields nothing."""
        first_human = next((m for m in self._history
                            if m.__class__.__name__ == "HumanMessage"), None)
        if first_human is None:
            return
        title = await agent.generate_title(agent.chunk_text(first_human))
        if title and self._conv_id and self._project_id:
            store.write_meta(self._project_id, self._conv_id, title=title)
            self.set_tab_title(title)

    _GATE_VERB = {"edit_file": "make this edit to", "write_file": "write",
                  "run_shell": "run"}

    async def _approve(self, tool_name: str, args: dict) -> bool:
        """Permission gate for a mutating tool. Returns True to proceed. The HITL
        mode (auto-edit/accept-all), a per-tool 'allow all this session', and the
        config policy each bypass the prompt. Shown inline as the Selection HITL
        while the tool is paused mid-execution (Phase-0 mechanism).

        ToolNode runs concurrent tool_calls in parallel, so the interactive prompt is
        serialized under _hitl_lock — two approvals can't mount overlapping Selections.
        The fast-path bypasses are checked outside the lock (no need to queue)."""
        if self._hitl_mode.auto_approves(tool_name) or tool_name in self._approved_all:
            return True
        if self._policy.auto_allow(tool_name, args):
            return True
        async with self._hitl_lock:
            # Re-check inside the lock: a sibling approval that ran while we waited may
            # have flipped the mode or added this tool to 'allow all this session'.
            if self._hitl_mode.auto_approves(tool_name) or tool_name in self._approved_all:
                return True
            verb = self._GATE_VERB.get(tool_name, tool_name)
            target = args.get("path") or args.get("command") or ""
            idx, _ = await self.ask_choice(
                f"Do you want to {verb} {target}?",
                ["Yes", "Yes (allow all this session)", "No"],
                recommended=0, connected=True)
            # One-time coachmark (#3): the first time the gate ever asks, teach the
            # shortcuts so repeat prompts don't feel like friction.
            if ui_state.mark_shown("coach_approval"):
                await self._mount_hint(
                    self.query_one("#log", VerticalScroll),
                    "tip: 'allow all this session' stops repeat asks for this tool · "
                    "shift+tab → auto-edit lets file writes through automatically")
            if idx == 1:
                self._approved_all.add(tool_name)
                return True
            return idx == 0

    async def _render_tool_result(self, node, name: str, args, output: str) -> None:
        """Render a finished tool call into the right Style-B body, by tool type:
        edit→diff, write→created content, shell→output/exit (failure on non-zero),
        read/list→plain output. edit/write bodies come from the INPUT args (the
        tools return only a confirmation string)."""
        args = args if isinstance(args, dict) else {}

        if name == "edit_file":
            if output.startswith("ERROR"):
                node.set_rail("failed"); self._turn_had_error = True
                await node.set_failure("", output)
                return
            changes = ([("del", ln) for ln in args.get("old_string", "").splitlines()]
                       + [("add", ln) for ln in args.get("new_string", "").splitlines()])
            adds = sum(1 for k, _ in changes if k == "add")
            dels = sum(1 for k, _ in changes if k == "del")
            node.set_rail(f"+{adds} −{dels}")
            await node.set_body(CleanDiff(args.get("path", ""), changes), collapsed=True)
            node.set_status("complete")
            return

        if name == "write_file":
            if output.startswith("ERROR"):
                node.set_rail("failed"); self._turn_had_error = True
                await node.set_failure("", output)
                return
            lines = (args.get("content", "") or "").splitlines() or [""]
            node.set_rail(f"{len(lines)} lines")
            await node.set_body(ToolOutput(lines), collapsed=True)
            node.set_status("complete")
            return

        if name == "run_shell":
            m = re.search(r"\[exit:\s*(-?\d+)\]", output)
            exit_code = int(m.group(1)) if m else 0
            if exit_code != 0:
                node.set_rail(f"exit {exit_code}")
                await node.set_failure(output, f"exit {exit_code}")
                return
            node.set_rail("exit 0")
            await node.set_body(ToolOutput(output.splitlines() or [""]), collapsed=True)
            node.set_status("complete")
            return

        # read_file / list_files / unknown → plain output (or a reported error)
        if output.startswith("ERROR"):
            node.set_rail("failed")
            await node.set_failure("", output)
            return
        lines = output.splitlines() or [""]
        noun = {"list_files": "items", "list_tree": "entries"}.get(name, "lines")
        node.set_rail(f"{len(lines)} {noun}")
        await node.set_body(ToolOutput(lines), collapsed=True)   # collapsed; click to expand
        node.set_status("complete")
