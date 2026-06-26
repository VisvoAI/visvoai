"""
demo.py — DemoMixin: the scripted /demo showcase (mock data), isolated from the
real agent loop.

These methods render the use-case arcs (Case A–G + the showcase _run_turn) with
mock data and demo pacing — the design/verify surface, reachable only via /demo
and the Ctrl-key demo actions. Kept OUT of app.py so the real-agent integration
code stays the focus. The mixin uses shared primitives defined on VisvoApp
(_begin_turn, _mount_block, _tool_node, ask_choice/ask_form, etc.) via self.
"""
from __future__ import annotations

import asyncio
import os
import re

from textual.containers import VerticalScroll

from visvoai.cli.mock import (
    BIG_DIFF,
    CASE_B_BACKTRACKS,
    CASE_B_DIAGNOSE_THINK,
    CASE_B_FIX_DIFF,
    CASE_B_GREP_TIMEOUT,
    CASE_B_HYPOTHESIS_REPLY,
    CASE_B_POOL_CONFIG,
    CASE_B_READ_CHAIN,
    CASE_B_RECONCILE,
    CASE_B_THINK_OPEN,
    CASE_B_TIMEOUT_FINDING,
    CONFIG_RATE_DIFF,
    DEMO_BACKEND_TABLE,
    DEMO_FORM_FIELDS,
    DEMO_INTRO,
    DEMO_PLAN,
    DEMO_SUMMARY,
    DIR_TREE,
    GREP_RESULTS,
    LONG_OUTPUT,
    MAIN_PY,
    MAIN_REGISTER_DIFF,
    MIDDLEWARE_DIFF,
    MIDDLEWARE_FIX_DIFF,
    SHELL_FAIL,
    SHELL_PASS,
    gen_ci_log,
    gen_pytest_flaky_50,
    gen_pytest_verify_50,
    THINKING_DIAGNOSE,
    THINKING_PLAN,
    # Case A
    CASE_A_THINK, CASE_A_INTRO, CASE_A_PLAN, CASE_A_GREP_PRINT, CASE_A_UTILS_DIFF,
    CASE_A_UTILS_DIFF2, CASE_A_UTILS_DIFF3, CASE_A_RESCAN_GREP, CASE_A_ITEMS_DIFF,
    CASE_A_TEST_FIX_DIFF, CASE_A_SUMMARY,
    # Case C
    CASE_C_PLAN, CASE_C_DEPS, CASE_C_PROPOSAL, CASE_C_MODEL_DIFF, CASE_C_ROUTE_DIFF,
    CASE_C_CURSOR_ROUTE_DIFF, CASE_C_RECONCILE,
    # Case E
    CASE_E_STACK_ANNOTATION, CASE_E_READ_CHAIN, CASE_E_FIX_DIFF,
    gen_full_suite_then_break, gen_checkout_subset,
    # Case F
    CASE_F_LAYOUT, CASE_F_FILES, CASE_F_INTRO, CASE_F_SUMMARY, gen_scaffold_install,
    # Case G
    CASE_G_CITATION, CASE_G_PLAN, CASE_G_GREP, CASE_G_GET_DIFF, CASE_G_GET_DIFF2,
    CASE_G_NARRATIVE_EXCERPT, CASE_G_NARRATIVE_ANNOTATION, CASE_G_REL_DIFF,
    CASE_G_WARN_FLOOD, CASE_G_SUMMARY,
)
from visvoai.cli.widgets import (
    Assistant,
    Citation,
    CleanDiff,
    CompactionMarker,
    ErrorBlock,
    FileCreation,
    Plan,
    ReadChainGroup,
    ReconciliationBlock,
    SeverityOutput,
    StatusBar,
    StreamingOutput,
    StructureTree,
    SystemNote,
    Thinking,
    ToolGroup,
    ToolNode,
    ToolOutput,
)


def _stream_chunks(text: str) -> list[str]:
    """Split text into word-sized chunks that PRESERVE whitespace (incl. newlines),
    so streaming markdown a chunk at a time reconstructs the source exactly and the
    block structure (lists, fences, headings) survives mid-stream."""
    return re.findall(r"\S+\s*", text) or ([text] if text else [])


class DemoMixin:
    """Scripted mock-data demo turns. Mixed into VisvoApp; calls shared helpers via self."""

    async def _pause(self, base: float) -> None:
        """Sleep `base` seconds scaled by the demo pace (tests run near-instant)."""
        await asyncio.sleep(base * self._pace)
    async def _stream_reply(self, log: VerticalScroll, text: str) -> Assistant:
        """Stream a markdown reply into a fresh Assistant block at a readable pace."""
        a = Assistant()
        await self._mount_block(log, a, "answer")
        for chunk in _stream_chunks(text):
            await a.add(chunk)
            log.scroll_end(animate=False)
            await self._pause(0.035)
        return a
    async def _think(self, log: VerticalScroll, text: str, status: str = "thinking…") -> None:
        """Stream a reasoning block, then collapse it to a summary. Self-cleans on
        cancel so the spinner interval never fires on a torn-down widget."""
        self._set_status(status)
        t = Thinking()
        await self._mount_block(log, t, "think")
        try:
            for word in text.split(" "):
                t.add(word + " ")
                log.scroll_end(animate=False)
                await self._pause(0.03)
            t.done()
            await self._pause(0.4)
        except asyncio.CancelledError:
            t.stop()
            raise
    @staticmethod
    def _diff_rail(changes) -> str:
        adds = sum(1 for k, _ in changes if k == "add")
        dels = sum(1 for k, _ in changes if k == "del")
        return f"+{adds} −{dels}"
    def _rail_for(self, body) -> str:
        """A sensible default right-rail derived from the body widget."""
        if isinstance(body, CleanDiff):
            return self._diff_rail(body.changes)
        if isinstance(body, ToolOutput):
            return f"{len(body.lines)} lines"
        return ""
    async def _run_tool(self, log: VerticalScroll, name: str, args: str,
                        body, status_msg: str, rail: str | None = None) -> ToolNode:
        """A tool node on the wire: pending → running → complete, body attached
        COLLAPSED (one click away). The right-rail defaults from the body."""
        self._set_status(status_msg)
        node = await self._tool_node(log, name, args)
        await self._pause(0.4)
        node.set_status("running")
        await self._pause(0.6)
        node.set_rail(rail if rail is not None else self._rail_for(body))
        await node.set_body(body, collapsed=True)
        node.set_status("complete")
        log.scroll_end(animate=False)
        await self._pause(0.4)
        return node
    async def _run_failing_tool(self, log: VerticalScroll, name: str, args: str,
                                output, error, status_msg: str,
                                rail: str = "") -> ToolNode:
        """A tool that runs then ERRORS — output + error attach to the node as a
        lean connected body (`set_failure`), never an orphaned ErrorBlock."""
        self._set_status(status_msg)
        node = await self._tool_node(log, name, args)
        await self._pause(0.4)
        node.set_status("running")
        await self._pause(0.6)
        node.set_rail(rail)
        await node.set_failure(output, error)
        log.scroll_end(animate=False)
        await self._pause(0.4)
        return node
    async def _run_long_shell(self, log: VerticalScroll, command: str, line_gen,
                              status_msg: str, final_status: str = "complete") -> ToolNode:
        """A run_shell node: stream lines into a StreamingOutput body, then mark
        complete. Esc mid-stream cancels the generator but the partial output stays
        on the node (interrupt-keep-partial).

        Mounts EXPANDED while running (the live tail is the point) and collapses on
        completion. On cancel it freezes the body and sets status `stopped`, then
        re-raises so the turn worker's cancel propagates."""
        self._set_status(status_msg)
        node = await self._tool_node(log, "run_shell", command)
        await self._pause(0.4)
        node.set_status("running")

        body = StreamingOutput(max_lines=12)
        await node.set_body(body, collapsed=False)   # EXPANDED while running
        log.scroll_end(animate=False)

        try:
            async for line in line_gen:
                body.add_line(line)
                log.scroll_end(animate=False)
                await self._pause(0.04)
            node.set_status(final_status)
        except asyncio.CancelledError:
            body.finalize()
            node.set_status("stopped")   # the run happened, partially
            raise                        # let the turn worker's cancel propagate
        finally:
            body.finalize()

        node.set_rail(f"{len(body.lines())} lines")
        node.set_collapsed(True)
        await self._pause(0.4)
        return node
    async def _run_read_chain(self, log: VerticalScroll, label: str,
                              reads: list[tuple[str, str, list[str]]],
                              backtracks: list[int] | None = None) -> ReadChainGroup:
        """Mount a `ReadChainGroup`, add a wired read node per hop (call → running →
        body, collapsed), then mark the dead-end backtracks. Reads are
        `(tool, args, output_lines)` tuples; bodies are collapsed `ToolOutput`s."""
        chain = ReadChainGroup(label)
        # "chain" (not "tool") so the next standalone tool gets a gap and doesn't
        # read as one more row of the chain.
        await self._mount_block(log, chain, "chain")
        for tool, args, lines in reads:
            node = ToolNode(tool, args, rail=f"{len(lines)} lines")
            await chain.add_node(node)
            await self._pause(0.3)
            node.set_status("running")
            await self._pause(0.4)
            await node.set_body(ToolOutput(lines, max_lines=8), collapsed=True)
            node.set_status("complete")
            log.scroll_end(animate=False)
        for idx in backtracks or []:
            chain.mark_backtrack(idx)
        await self._pause(0.4)
        return chain
    async def _edit_with_approval(self, log: VerticalScroll, path: str,
                                  changes, prompt: str | None = None) -> bool:
        """An update node with a syntax diff, then an inline approval HITL. The diff
        shows EXPANDED for review, then folds once they answer. The node's own
        status (✓ complete / ✗ denied) is the outcome — no redundant 'updated X'
        note. Returns True if applied."""
        node = await self._tool_node(log, "update_file", path,
                                     rail=self._diff_rail(changes))
        await self._pause(0.4)
        node.set_status("running")
        await self._pause(0.6)
        await node.set_body(CleanDiff(path, changes), collapsed=False)
        log.scroll_end(animate=False)
        self._set_status("waiting for approval…")
        if prompt is None:
            prompt = f"Do you want to make this edit to {os.path.basename(path)}?"
        idx, note = await self.ask_choice(
            prompt, ["Yes", "Yes, allow all edits this session", "No"],
            recommended=0, connected=True)
        applied = idx in (0, 1)   # 0 = yes · 1 = yes (allow all) · 2 = no
        node.set_status("complete" if applied else "denied")
        if note:
            node.set_rail(f"{self._diff_rail(changes)} · {note}")
        node.set_collapsed(True)  # decision made → fold the diff away
        await self._pause(0.4)
        return applied
    async def _demo_picker(self) -> None:
        idx, _ = await self.ask_choice(
            "Run a demo case:",
            [
                "Smoke — vocabulary (current /demo)",
                "A — Cross-module refactor",
                "B — Flaky test diagnosis",
                "C — Feature build w/ redirection",
                "D — Resume a half-finished task",
                "E — Incident response / hotfix",
                "F — Greenfield scaffold",
                "G — Dependency upgrade",
            ],
            recommended=0,
        )
        if idx is None:
            return  # cancelled the picker
        arcs = {
            0: lambda: self._run_turn("add an anthropic provider to my config"),
            1: self._run_case_a,
            2: self._run_case_b,
            3: self._run_case_c,
            5: self._run_case_e,
            6: self._run_case_f,
            7: self._run_case_g,
        }
        if idx in arcs:
            self._turn_worker = self.run_worker(arcs[idx](), exclusive=True)
        else:
            # Case D (resume) is integration-flavoured — deferred, not mocked here.
            log = self.query_one("#log", VerticalScroll)
            await self._mount_block(log, SystemNote(
                "Case D (resume) is deferred to integration — it needs real "
                "persistence the mock phase can't fake", kind="info"), "note")
    async def _run_case_b(self) -> None:
        """Case B — Flaky test diagnosis, the full 6-turn arc.

        Turn 1 clarification loop (two `ask_text`, vague → sharp) → Turn 2 multi-hop
        read chain (`ReadChainGroup`, one backtrack collapsed) → Turn 3 long-running
        shell (`_run_long_shell`, the 50× flake reproduction) → Turn 4 overflowing CI
        log (`ToolOutput(tier2=True)`) + a diagnosis reply → Turn 5
        hypothesis + fix (`CleanDiff` + approval) → Turn 6 interrupt + redirect +
        `ReconciliationBlock` → grep → finding. The live demo waits for human HITL
        input; tests drive resolution via the widgets' `_resolve()`."""
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "test_checkout_concurrent passes locally but fails "
                                    "in CI ~30% of the time. Find the race.")

        # Agent thinks briefly, then asks for the failing run (free-text HITL).
        await self._think(log, CASE_B_THINK_OPEN, status="thinking…")

        # First ask — open question, user answers vaguely.
        self._set_status("waiting for clarification…")
        vague = await self.ask_text(
            "Which CI run failed? Paste the URL or the failure stack.",
            placeholder="e.g. the tuesday run, or paste the traceback…",
        )
        if vague is None:
            await self._mount_block(log, SystemNote("(cancelled)", kind="stopped"), "note")
            self._set_status(None)
            return
        await self._mount_block(log, SystemNote(f"you said: {vague!r}", kind="info"), "note")

        # Agent re-asks sharper (the clarification loop).
        self._set_status("waiting for clarification…")
        sharp = await self.ask_text(
            "Can you paste the actual failure stack trace? I need the assertion "
            "line and the exception type.",
            placeholder="paste the traceback here…",
        )
        if sharp is None:
            await self._mount_block(log, SystemNote("(cancelled — stopping)", kind="stopped"), "note")
            self._set_status(None)
            return
        await self._mount_block(log, SystemNote(
            "received the trace — starting diagnosis", kind="info"), "note")

        # ── Turn 2: multi-hop read chain (test → fixture → service → helper) ──
        self._set_status("reading files…")
        await self._run_read_chain(log, "tracing the race",
                                   CASE_B_READ_CHAIN, backtracks=CASE_B_BACKTRACKS)

        # ── Turn 3: long-running shell to reproduce the flake ──
        await self._run_long_shell(
            log,
            "pytest -q tests/test_checkout_concurrent.py --count=50",
            gen_pytest_flaky_50(),
            status_msg="running tests (50 iterations)…",
            final_status="failed",   # the suite failed — render as not-complete
        )

        # ── Turn 4: read the CI log (overflowing, tier-2), then diagnose ──
        await self._run_tool(log, "read_file", "ci_logs/run_2847.log",
                             ToolOutput(gen_ci_log(), max_lines=12, tier2=True),
                             status_msg="reading CI log (2000 lines)…")
        await self._think(log, CASE_B_DIAGNOSE_THINK, status="analyzing the race…")

        # ── Turn 5: confirm the hypothesis + propose the fix ──
        await self._run_tool(log, "read_file", "api/config.toml",
                             ToolOutput(CASE_B_POOL_CONFIG, max_lines=8),
                             status_msg="reading pool config…")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_B_HYPOTHESIS_REPLY)
        await self._edit_with_approval(log, "checkout/db.py", CASE_B_FIX_DIFF,
                                       prompt="Apply this fix?")

        # ── Turn 6: verify → mid-run redirect → reconcile → address it ──
        await self._run_case_b_turn6(log)

        self._set_status(None)
    async def _run_case_b_turn6(self, log: VerticalScroll) -> None:
        """Turn 6 — verify the fix (a second 50× run), get redirected mid-run, and
        reconcile instead of restarting: keep the partial verification, drop the
        full re-run, add the timeout check. The redirect is scripted (the stream
        breaks at run 23) — the live `_pending_redirect` queue is the production
        path; here we drive it directly so the demo is self-contained."""
        self._set_status("verifying fix…")
        node = await self._tool_node(
            log, "run_shell", "pytest -q tests/test_checkout_concurrent.py --count=50")
        await self._pause(0.4)
        node.set_status("running")
        body = StreamingOutput(max_lines=12)
        await node.set_body(body, collapsed=False)   # EXPANDED while running
        log.scroll_end(animate=False)

        count = 0
        async for line in gen_pytest_verify_50():
            body.add_line(line)
            log.scroll_end(animate=False)
            await self._pause(0.04)
            count += 1
            if count == 23:
                # The user redirects mid-run; the agent stops to reconcile.
                await self._mount_block(log, SystemNote(
                    "queued redirect: also check the connection timeout",
                    kind="info"), "note")
                break

        body.finalize()
        node.set_rail(f"{len(body.lines())} lines · stopped")
        node.set_status("stopped")   # the run happened, partially
        node.set_collapsed(True)
        await self._pause(0.4)

        # The reconciliation — what's kept, reverted, added.
        await self._mount_block(log, ReconciliationBlock(**CASE_B_RECONCILE), "note")

        # Address the redirect: grep for the timeout settings.
        await self._run_tool(log, "grep", "timeout",
                             ToolOutput(CASE_B_GREP_TIMEOUT, max_lines=8),
                             status_msg="searching for timeout settings…")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_B_TIMEOUT_FINDING)
        await self._mount_block(log, SystemNote(
            "found: tests/fixtures/pool.py sets timeout=0 — overriding the config",
            kind="info"), "note")
    async def _auto_edit(self, log: VerticalScroll, path: str, changes,
                         label: str = "auto-applied") -> ToolNode:
        """An edit that lands WITHOUT its own approval — the user pre-approved the
        pattern. Mounts collapsed + tags the rail (`auto-applied`/`pattern-applied`)."""
        node = await self._tool_node(log, "update_file", path)
        await self._pause(0.3)
        node.set_status("running")
        await self._pause(0.3)
        node.set_rail(self._diff_rail(changes))
        await node.set_body(CleanDiff(path, changes), collapsed=True)
        node.mark_auto_applied(label)
        log.scroll_end(animate=False)
        await self._pause(0.3)
        return node
    async def _run_case_a(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "Migrate every print() call in the codebase to "
                                    "the structured logger. Keep the tests green.")
        await self._mount_block(log, SystemNote(
            "created branch agent/print-to-logger", kind="branch"), "note")
        await self._think(log, CASE_A_THINK)
        self._set_status("responding…")
        await self._stream_reply(log, CASE_A_INTRO)

        plan = Plan(CASE_A_PLAN)
        await self._pin_plan(plan)

        # step 0 — map every call site
        plan.start(0)
        await self._run_tool(log, "grep", '"print(" -r .',
                             ToolOutput(CASE_A_GREP_PRINT, max_lines=10),
                             "mapping call sites…")
        plan.complete(0)

        # step 1 — utils.py: approve once, then auto-apply the identical pattern
        plan.start(1)
        await self._edit_with_approval(log, "utils.py", CASE_A_UTILS_DIFF,
                                       prompt="Apply this print→logger change?")
        await self._mount_block(log, SystemNote(
            "approved the print→logger pattern — applying the rest automatically",
            kind="info"), "note")
        await self._auto_edit(log, "utils.py", CASE_A_UTILS_DIFF2)
        await self._auto_edit(log, "utils.py", CASE_A_UTILS_DIFF3)
        plan.complete(1)

        # step 2 — routes/: a re-scan finds sites the first grep missed → INSERT a step
        plan.start(2)
        await self._auto_edit(log, "routes/items.py", CASE_A_ITEMS_DIFF)
        await self._run_tool(log, "grep", '"print(" routes/',
                             ToolOutput(CASE_A_RESCAN_GREP, max_lines=8),
                             "re-scanning routes/…")
        await plan.insert(3, "re-scan for missed sites")
        await self._mount_block(log, SystemNote(
            "found 2 sites a recursive import hid — inserted a re-scan step",
            kind="info"), "note")
        plan.complete(2)

        # step 3 (inserted) — the missed sites
        plan.start(3)
        await self._auto_edit(log, "routes/_legacy.py", CASE_A_ITEMS_DIFF)
        plan.complete(3)

        # stale-read conflict: a prior edit moved line numbers → reject + re-read
        await self._mount_block(log, SystemNote(
            "routes/health.py changed since I read it — re-reading before editing",
            kind="stale"), "note")
        await self._run_tool(log, "read_file", "routes/health.py",
                             ToolOutput(["# re-read — line numbers shifted +2"], max_lines=4),
                             "re-reading routes/health.py…")
        await self._auto_edit(log, "routes/health.py", CASE_A_ITEMS_DIFF)

        # compaction mid-task — the pinned plan survives intact
        await self._mount_block(log, CompactionMarker(
            "12 files read + 13 edits folded  ·  68% → 22% context"), "note")
        self._set_context(22)
        await self._mount_block(log, SystemNote(
            "context compacted — the plan is intact, continuing at step 4",
            kind="info"), "note")

        # step 4 — tests/ (the caplog fix)
        plan.start(4)
        await self._auto_edit(log, "tests/test_load.py", CASE_A_TEST_FIX_DIFF)
        plan.complete(4)

        # step 5 — run the suite + verify
        plan.start(5)
        await self._run_tool(log, "run_shell", "pytest -q",
                             ToolOutput(["41 passed in 2.1s"], max_lines=4),
                             "running the suite…")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_A_SUMMARY)
        plan.complete(5)
        await self._mount_block(log, SystemNote(
            "refactor complete — review the 11-file change set with /commit (Ctrl+G)",
            kind="branch"), "note")
        self._set_status(None)
        await self._unpin_plan()
    async def _run_case_c(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "Add pagination to the items API.")
        sb = self.query_one("#status", StatusBar)

        # Turn 1 — plan mode: read + propose, no edits yet
        sb.set_mode("plan")
        await self._mount_block(log, SystemNote(
            "plan mode — I'll propose an approach and won't edit until you unlock",
            kind="info"), "note")
        await self._run_read_chain(log, "reading the API", [
            ("read_file", "routes/items.py", ["@router.get('/items')", "def list(): ..."]),
            ("read_file", "models/item.py", ["class ItemQuery(BaseModel): ..."]),
        ])
        self._set_status("responding…")
        await self._stream_reply(log, CASE_C_PROPOSAL)
        plan = Plan(CASE_C_PLAN, deps=CASE_C_DEPS)
        await self._pin_plan(plan)

        idx, _ = await self.ask_choice(
            "Unlock execution and implement this?",
            ["Yes, implement offset pagination", "Stay in plan mode"], recommended=0)
        if idx != 0:
            sb.set_mode(None)
            await self._mount_block(log, SystemNote("staying in plan mode", kind="info"), "note")
            self._set_status(None)
            return
        sb.set_mode(None)
        await self._mount_block(log, SystemNote("execution unlocked", kind="info"), "note")
        plan.complete(0)

        # Turn 2 — implement offset, ordered: model BEFORE route
        plan.start(1)
        await self._auto_edit(log, "models/item.py", CASE_C_MODEL_DIFF)
        plan.complete(1)
        plan.start(2)
        await self._auto_edit(log, "routes/items.py", CASE_C_ROUTE_DIFF)
        plan.complete(2)
        plan.start(3)  # writing offset tests when the redirect lands

        # Turn 3 — mid-impl redirect → reconcile (not restart)
        await self._mount_block(log, SystemNote(
            "queued redirect: actually make it cursor-based, not offset", kind="info"), "note")
        await self._mount_block(log, ReconciliationBlock(**CASE_C_RECONCILE), "note")

        # Turn 4 — plan mutation: supersede the offset route + tests, branch to cursor
        await plan.supersede(2, replacement="implement cursor (keyset) pagination")
        # the offset-tests step shifted to index 4 after the insert above
        await plan.supersede(4, replacement="rewrite tests for cursor")
        await self._mount_block(log, SystemNote(
            "offset route + tests superseded — switching to cursor", kind="info"), "note")

        # Turn 5 — clarification loop (free-text → choice)
        self._set_status("waiting for clarification…")
        how = await self.ask_text(
            "Cursor-based how — keyset on `id`, or an opaque token?",
            placeholder="describe the cursor…")
        if how is None:
            await self._mount_block(log, SystemNote("(cancelled)", kind="stopped"), "note")
            self._set_status(None)
            return
        enc_idx, _ = await self.ask_choice(
            "Encode the cursor as:", ["Opaque base64 of the last id", "A signed token"],
            recommended=0)
        enc = ["base64", "signed"][enc_idx if enc_idx is not None else 0]
        await self._mount_block(log, SystemNote(
            f"cursor: {how!r} · {enc}", kind="info"), "note")

        # Turn 6 — implement cursor (step 3), rewrite tests (step 5), run suite (step 6)
        plan.start(3)
        await self._auto_edit(log, "routes/items.py", CASE_C_CURSOR_ROUTE_DIFF)
        plan.complete(3)
        plan.start(5)
        await self._auto_edit(log, "tests/test_items.py",
                              [("add", "def test_cursor_page(client): ...")])
        plan.complete(5)
        plan.start(6)
        await self._run_tool(log, "run_shell", "pytest -q tests/test_items.py",
                             ToolOutput(["4 passed in 0.6s"], max_lines=4),
                             "running pagination tests…")
        plan.complete(6)
        await self._mount_block(log, SystemNote(
            "cursor pagination shipped — review with /commit (Ctrl+G)", kind="branch"), "note")
        self._set_status(None)
        await self._unpin_plan()
    async def _run_case_e(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "Inc-2241: checkout endpoint 500ing for ~2% of "
                                    "requests since the deploy. Here's the stack: "
                                    "[pastes 500-line trace]")
        # The large paste is summarised, not dumped (PromptArea.LargePaste signal).
        await self._mount_block(log, SystemNote(
            "pasted stack trace · 500 lines", kind="info"), "note")
        await self._think(log, "Scanning the trace for the first frame in our code…",
                          status="reading the stack…")
        # The pasted stack is the input (noted above); the agent's read of it is
        # prose, not an orphaned error block.
        self._set_status("responding…")
        await self._stream_reply(log, CASE_E_STACK_ANNOTATION)

        await self._run_read_chain(log, "tracing the null deref", CASE_E_READ_CHAIN)

        await self._mount_block(log, SystemNote(
            "created worktree hotfix/inc-2241 (isolated from your checkout)",
            kind="branch"), "note")

        # expedited approval — one-line guard, no heavy chrome (compact Selection)
        node = await self._tool_node(log, "update_file", "checkout/deserialize.py",
                                     rail=self._diff_rail(CASE_E_FIX_DIFF))
        await self._pause(0.3)
        node.set_status("running")
        await self._pause(0.4)
        await node.set_body(CleanDiff("checkout/deserialize.py", CASE_E_FIX_DIFF),
                            collapsed=False)
        self._set_status("waiting for approval…")
        idx, _ = await self.ask_choice("Apply the one-line guard?", ["Apply", "Skip"],
                                       recommended=0, connected=True, compact=True)
        applied = idx == 0
        node.set_status("complete" if applied else "denied")
        node.set_collapsed(True)
        await self._mount_block(log, SystemNote(
            "guard applied" if applied else "skipped", kind="info" if applied else "stopped"),
            "note")

        # narrow-scope interrupt: full suite → user wants it fast → switch to subset
        self._set_status("running full suite…")
        node2 = await self._tool_node(log, "run_shell", "pytest -q")
        await self._pause(0.3)
        node2.set_status("running")
        body = StreamingOutput(max_lines=12)
        await node2.set_body(body, collapsed=False)
        n = 0
        async for line in gen_full_suite_then_break():
            body.add_line(line)
            log.scroll_end(animate=False)
            await self._pause(0.05)
            n += 1
            if n == 3:
                await self._mount_block(log, SystemNote(
                    "queued redirect: just the checkout tests — I need this out fast",
                    kind="info"), "note")
                break
        body.finalize()
        node2.set_rail(f"{len(body.lines())} lines · stopped")
        node2.set_status("stopped")
        node2.set_collapsed(True)
        await self._pause(0.3)
        await self._mount_block(log, SystemNote(
            "narrowing scope — running only the checkout tests (partial suite output kept)",
            kind="info"), "note")
        await self._run_long_shell(log, "pytest -q tests/test_checkout.py",
                                   gen_checkout_subset(), status_msg="running checkout tests…")

        await self._mount_block(log, SystemNote(
            "hotpatch ready on hotfix/inc-2241 — /commit to stage", kind="branch"), "note")
        await self._mount_block(log, SystemNote(
            "reminder: this fix is on hotfix/inc-2241, NOT on main — cherry-pick it "
            "and deploy yourself (the CLI can't)", kind="info"), "note")
        self._set_status(None)
    async def _run_case_f(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "Scaffold a FastAPI service for the orders domain "
                                    "from this spec: [endpoints, data model, persistence TBD]")
        await self._mount_block(log, SystemNote("pasted spec · 42 lines", kind="info"), "note")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_F_INTRO)

        # Turn 1 — clarification: two choices (free-text fallback exists, same primitive)
        self._set_status("waiting for choices…")
        orm, _ = await self.ask_choice("Which ORM?", ["SQLAlchemy", "Raw SQL"], recommended=0)
        db, _ = await self.ask_choice("Which database?", ["Postgres", "SQLite"], recommended=0)
        orm_s = ["SQLAlchemy", "raw SQL"][orm if orm is not None else 0]
        db_s = ["Postgres", "SQLite"][db if db is not None else 0]
        await self._mount_block(log, SystemNote(f"using {orm_s} + {db_s}", kind="info"), "note")

        # Turn 2 — propose the structure as a reviewable tree
        await self._mount_block(log, StructureTree(CASE_F_LAYOUT), "note")
        idx, _ = await self.ask_choice("Generate this structure?",
                                       ["Yes, scaffold it", "Let me adjust"], recommended=0)
        if idx != 0:
            await self._mount_block(log, SystemNote("holding — adjust the structure", kind="info"), "note")
            self._set_status(None)
            return

        # Turn 3 — bulk creation in dependency order, joined on one wire
        self._set_status("generating files…")
        group = ToolGroup()
        await self._mount_block(log, group, "tool")
        for path, content in CASE_F_FILES:
            await group.add(FileCreation(path, content))
            await self._pause(0.25)

        # Turn 5 — first-run verification (deps install + suite)
        await self._run_long_shell(log, "pip install -e . && pytest -q",
                                   gen_scaffold_install(),
                                   status_msg="installing deps + first run…")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_F_SUMMARY)
        await self._mount_block(log, SystemNote(
            "scaffold ready — /commit to stage the 8 new files", kind="branch"), "note")
        self._set_status(None)
    async def _run_case_g(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()
        await self._begin_turn(log, "Upgrade SQLAlchemy from 1.4 to 2.0. The codebase "
                                    "uses the legacy Query API — migrate everything and "
                                    "keep tests green.")
        await self._mount_block(log, SystemNote(
            "created branch agent/sqlalchemy-2.0", kind="branch"), "note")

        # Turn 1 — quote the migration guide (the rule it follows, not a paraphrase)
        await self._think(log, "Pulling the 2.0 migration guide to get the exact rules "
                               "before touching code…", status="reading the migration guide…")
        await self._mount_block(log, Citation(**CASE_G_CITATION), "note")

        # Turn 2 — map usage, plan grouped by PATTERN (not by file)
        await self._run_tool(log, "grep", r'"\.query\." -r repo/',
                             ToolOutput(CASE_G_GREP, max_lines=8), "mapping Query usage…")
        self._set_status("responding…")
        await self._stream_reply(log, "20 call sites across 7 files. I'll migrate one "
                                      "**pattern** at a time, not one file at a time.")
        plan = Plan(CASE_G_PLAN)
        await self._pin_plan(plan)

        # Turn 3 — semantic migration: approve the pattern once, apply to the rest
        plan.start(0)
        await self._edit_with_approval(
            log, "repo/users.py", CASE_G_GET_DIFF,
            prompt="Apply the Query.get→Session.get migration to all 5 sites?")
        await self._mount_block(log, SystemNote(
            "approved the Query.get→Session.get pattern — applying to the other 4 sites",
            kind="info"), "note")
        await self._auto_edit(log, "repo/orders.py", CASE_G_GET_DIFF2, label="pattern-applied")
        plan.complete(0)
        plan.start(1)
        await self._auto_edit(log, "repo/orders.py",
                              [("del", "Order.query.filter(Order.open)"),
                               ("add", "session.scalars(select(Order).filter(Order.open)).all()")],
                              label="pattern-applied")
        plan.complete(1)
        plan.start(2)
        await self._auto_edit(log, "repo/items.py",
                              [("del", "Item.query.all()"),
                               ("add", "session.scalars(select(Item)).all()")],
                              label="pattern-applied")
        plan.complete(2)

        # compaction mid-migration — the migration map (plan) survives
        await self._mount_block(log, CompactionMarker(
            "migration map + 20 reads folded  ·  72% → 19% context"), "note")
        self._set_context(19)
        await self._mount_block(log, SystemNote(
            "context compacted — the migration map is intact, 3/5 patterns done",
            kind="info"), "note")

        # Turn 4 — a breaking change: the test fails (output connected to the run),
        # then the agent explains the 2.0 semantics in prose and fixes it.
        plan.start(3)
        await self._run_failing_tool(
            log, "run_shell", "pytest -q tests/test_orders.py",
            CASE_G_NARRATIVE_EXCERPT[:-1], CASE_G_NARRATIVE_EXCERPT[-1],
            status_msg="running orders tests…", rail="1 failed")
        self._set_status("responding…")
        await self._stream_reply(log, CASE_G_NARRATIVE_ANNOTATION)
        await self._auto_edit(log, "repo/orders.py", CASE_G_REL_DIFF, label="pattern-applied")
        plan.complete(3)

        # Turn 5 — deprecation-warning flood: severity-aware, foldable output
        plan.start(4)
        await self._run_tool(log, "run_shell", "pytest -q",
                             SeverityOutput(CASE_G_WARN_FLOOD),
                             "running the full suite…")
        plan.complete(4)

        # Turn 7 — summary + commit
        self._set_status("responding…")
        await self._stream_reply(log, CASE_G_SUMMARY)
        await self._mount_block(log, SystemNote(
            "upgrade complete — review the 7-file change set with /commit (Ctrl+G)",
            kind="branch"), "note")
        self._set_status(None)
        await self._unpin_plan()
    async def _run_turn(self, user_text: str) -> None:
        """The showcase turn — a realistic multi-file feature build that exercises the
        WHOLE vocabulary: branch note → planning thinking → markdown reply → a LIVE
        plan tracker → explore tools (list/grep/read) → a decision HITL (with a table)
        → a syntax-highlighted implementation + approval → tests that FAIL → diagnosis
        thinking → a fix → tests that PASS → a config form HITL → a rich markdown
        summary. This is the demo/verify surface AND the one method integration
        rewrites to stream real data."""
        log = self.query_one("#log", VerticalScroll)
        await self._unpin_plan()  # clear any plan pinned by a previous turn
        await self._begin_turn(log, user_text)
        await self._mount_block(
            log, SystemNote("created branch agent/rate-limiting", kind="branch"), "note")

        # plan-forming reasoning, then the opening reply
        await self._think(log, THINKING_PLAN)
        self._set_status("responding…")
        await self._stream_reply(log, DEMO_INTRO)

        # the live plan tracker the rest of the turn drives — pinned above the input
        plan = Plan(DEMO_PLAN)
        await self._pin_plan(plan)

        # ── step 1 · explore the codebase ──
        plan.start(0)
        await self._run_tool(log, "list_dir", "api/",
                             ToolOutput(DIR_TREE, max_lines=12), "running list_dir…")
        await self._run_tool(log, "grep", '"FastAPI|include_router" api/',
                             ToolOutput(GREP_RESULTS, max_lines=10), "running grep…")
        await self._run_tool(log, "read_file", "api/main.py",
                             ToolOutput(MAIN_PY, max_lines=12), "running read_file…")
        plan.complete(0)
        await self._pause(0.6)

        # ── step 2 · choose a backend (markdown table + decision HITL) ──
        plan.start(1)
        await self._stream_reply(log, DEMO_BACKEND_TABLE)
        self._set_status("waiting for a decision…")
        idx, note = await self.ask_choice(
            "Which rate-limit backend should I use?",
            ["In-memory — single process", "Redis — shared, multi-worker",
             "Memcached — shared, multi-worker"],
            recommended=0)
        chosen = ["in-memory", "Redis", "Memcached"][idx if idx is not None else 0]
        await self._mount_block(log, SystemNote(
            f"using the {chosen} backend" + (f" — {note}" if note else ""), kind="info"), "note")
        plan.complete(1)
        await self._pause(0.6)

        # ── step 3 · implement the middleware (syntax diff + approval) ──
        plan.start(2)
        await self._edit_with_approval(log, "api/middleware/limiter.py", MIDDLEWARE_DIFF)
        plan.complete(2)
        await self._pause(0.6)

        # ── step 4 · wire config + run tests (fail → diagnose → fix → pass) ──
        plan.start(3)
        await self._run_tool(log, "update_file", "api/main.py",
                             CleanDiff("api/main.py", MAIN_REGISTER_DIFF),
                             "updating api/main.py…")
        await self._run_failing_tool(
            log, "run_shell", "pytest -q tests/test_rate_limit.py",
            SHELL_FAIL,
            "exited code 1 — test_blocks_over_limit expected 429, got 503",
            "running tests…")
        await self._pause(0.5)
        await self._think(log, THINKING_DIAGNOSE, status="diagnosing the failure…")
        await self._run_tool(log, "update_file", "api/middleware/limiter.py",
                             CleanDiff("api/middleware/limiter.py", MIDDLEWARE_FIX_DIFF),
                             "updating api/middleware/limiter.py…")
        await self._mount_block(log, SystemNote(
            "fixed — return 429 with a Retry-After header", kind="info"), "note")
        await self._run_tool(log, "run_shell", "pytest -q tests/test_rate_limit.py",
                             ToolOutput(SHELL_PASS, max_lines=12), "re-running tests…")
        plan.complete(3)
        await self._pause(0.6)

        # ── step 5 · make limits configurable (form HITL) + summary ──
        plan.start(4)
        self._set_status("waiting for config…")
        await self.ask_form("Tune the rate limits (written to config.toml):", DEMO_FORM_FIELDS)
        await self._run_tool(log, "update_file", "api/config.toml",
                             CleanDiff("config.toml", CONFIG_RATE_DIFF), "updating api/config.toml…")
        self._set_status("responding…")
        await self._stream_reply(log, DEMO_SUMMARY)
        plan.complete(4)
        await self._mount_block(
            log, SystemNote("ready to commit — run /commit (Ctrl+G)", kind="branch"), "note")

        self._set_context((self._ctx_pct or 30) + 14)  # the turn consumed more context (mock)
        self._set_status(None)  # back to idle context info
        await self._unpin_plan()  # all todos done + turn over → the plan vanishes
    def action_permission(self) -> None:
        self.run_worker(self._choice_flow())
    async def _choice_flow(self) -> None:
        idx, note = await self.ask_choice(
            "How should the Anthropic provider get its API key?",
            ["Use ANTHROPIC_API_KEY env var", "Prompt me for the key now", "Store it in the config file"],
            recommended=0,
        )
        self.notify("cancelled" if idx is None else f"chose option {idx + 1}" + (f" — {note}" if note else ""))
    async def action_error_demo(self) -> None:
        """Demo the clean error states (tool error then model error)."""
        log = self.query_one("#log", VerticalScroll)
        await log.mount(ErrorBlock(
            "tool",
            "run_shell exited with code 1 while running `pytest`.",
            "2 failed, 18 passed — see the failing assertions above.",
        ))
        await log.mount(ErrorBlock(
            "model",
            "The model stream was interrupted before completing.",
            "Reason: rate limit reached. Retrying is safe.",
        ))
        log.scroll_end(animate=False)
    async def action_output_demo(self) -> None:
        """Demo collapsible long tool output + a large truncated diff."""
        log = self.query_one("#log", VerticalScroll)
        await log.mount(ToolOutput(LONG_OUTPUT, max_lines=10))
        await log.mount(CleanDiff("big_module.py", BIG_DIFF, max_lines=10, show_header=True))
        log.scroll_end(animate=False)
    def action_form_demo(self) -> None:
        self.run_worker(self._form_flow())
    async def _form_flow(self) -> None:
        """Demo the multi-field inline form HITL."""
        values = await self.ask_form(
            "Configure the new provider:",
            [
                ("name", "Provider name", "anthropic"),
                ("model", "Default model", "claude-opus-4-8"),
                ("key_env", "API key env var", "ANTHROPIC_API_KEY"),
            ],
        )
        self.notify("cancelled" if values is None else f"saved: {values}")
