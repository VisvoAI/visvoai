"""End-to-end: the rich /demo turn runs to completion through every HITL.

Auto-answers the decision/approval choices and the config form as they appear,
then asserts the full vocabulary showed up and the plan finished.
"""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import (
    ErrorBlock, Form, FreeText, OutputToolbar, Plan,
    ReadChainGroup, ReconciliationBlock, Selection, SystemNote, Thinking,
    ToolNode, ToolOutput,
)
from visvoai.cli.widgets.tool_row import ToolErrorBody
from visvoai.cli.widgets.prompt import PromptArea


async def _drive_case_b(app, pilot, max_iters: int = 12000) -> int:
    """Run the full Case B arc to completion, resolving the two clarification
    asks (FreeText) and the fix approval (Selection). Returns the ask count."""
    answers = ["the tuesday run", "TimeoutError: QueuePool limit reached"]
    asks = 0
    worker = app.run_worker(app._run_case_b(), exclusive=True)
    app._turn_worker = worker
    for _ in range(max_iters):
        await pilot.pause()
        fts = app.query(FreeText)
        if fts:
            fts.first()._resolve(answers[min(asks, len(answers) - 1)])
            asks += 1
            continue
        sels = app.query(Selection)
        if sels:
            sels.first()._resolve((0, ""))   # approve the fix
            continue
        if any("overriding the config" in n.message for n in app.query(SystemNote)):
            await worker.wait()
            return asks
    raise AssertionError("Case B full arc did not complete")


@pytest.mark.asyncio
async def test_demo_runs_through_all_hitls_to_completion():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.03  # run the demo fast in tests
        app.run_command("demo")

        done = False
        for _ in range(2000):
            await pilot.pause()
            sels = app.query(Selection)
            if sels:
                sels.first()._resolve((0, ""))      # take the recommended option
                continue
            forms = app.query(Form)
            if forms:
                forms.first()._resolve({})           # accept the form
                continue
            if any("ready to commit" in n.message for n in app.query(SystemNote)):
                done = True
            if done and not app.query(Plan):         # terminal note + plan vanished
                break

        assert done, "demo turn never reached its terminal 'ready to commit' note"
        # the turn completed normally (only reachable after plan.complete) and the
        # finished plan vanished
        assert not app.query(Plan), "completed plan should vanish when the turn ends"

        # the whole vocabulary appeared
        assert len(app.query(ToolNode)) >= 6         # list/grep/read/edit×3/shell×2
        assert len(app.query(Thinking)) == 2         # planning + diagnosing
        # the failing test surfaced CONNECTED to its tool (not an orphaned block)
        assert app.query(ToolErrorBody)
        assert not app.query(ErrorBlock)             # no orphaned error block


@pytest.mark.asyncio
async def test_case_b_turn1_runs_through_clarification():
    """Case B Turn 1: the clarification loop fires ask_text twice (vague → sharp)
    and reaches its terminal 'starting diagnosis' note."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.03
        worker = app.run_worker(app._run_case_b(), exclusive=True)

        answers = ["the tuesday run", "TimeoutError: QueuePool limit reached"]
        asks = 0
        done = False
        for _ in range(2000):
            await pilot.pause()
            fts = app.query(FreeText)
            if fts:
                fts.first()._resolve(answers[min(asks, len(answers) - 1)])
                asks += 1
                continue
            if any("starting diagnosis" in n.message for n in app.query(SystemNote)):
                done = True
                break

        assert asks == 2, "both clarification asks should have fired"
        assert done, "case B Turn 1 never reached its terminal note"
        # The arc continues past this checkpoint (Turns 2-6); this test only
        # verifies the Turn 1 clarification slice, so stop the worker here rather
        # than waiting for the full arc (which would park at a later HITL).
        worker.cancel()


@pytest.mark.asyncio
async def test_case_b_turn3_streams_full_flaky_run():
    """Case B Turn 1 → Turn 3: after the clarification loop, the long-running
    pytest stream runs and streams the full 50-run output."""
    from visvoai.cli.widgets import StreamingOutput

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        worker = app.run_worker(app._run_case_b(), exclusive=True)

        answers = ["the tuesday run", "TimeoutError: QueuePool limit reached"]
        asks = 0
        streamed = False
        for _ in range(4000):
            await pilot.pause()
            fts = app.query(FreeText)
            if fts:
                fts.first()._resolve(answers[min(asks, len(answers) - 1)])
                asks += 1
                continue
            outs = app.query(StreamingOutput)
            if outs and "23 passed, 27 failed in 52.3s" in outs.first().lines():
                streamed = True
                break

        assert asks == 2, "both clarification asks should have fired"
        assert streamed, "case B never streamed the full flaky-test run"
        # The arc continues past Turn 3 (Turns 4-6); this test verifies only the
        # long-shell slice, so stop the worker rather than awaiting full completion.
        worker.cancel()


@pytest.mark.asyncio
async def test_case_b_full_arc_completes():
    """Drive the full 6-turn Case B arc end-to-end and assert every turn's
    signature widget is present once the terminal note appears."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        asks = await _drive_case_b(app, pilot)

        assert asks == 2                                   # Turn 1: both asks fired
        assert len(app.query(ReadChainGroup)) == 1         # Turn 2: the read chain
        assert len(app.query(ReconciliationBlock)) == 1    # Turn 6: the reconcile
        # Turn 4: a tier-2 CI log output with a toolbar
        assert any(o.tier2 for o in app.query(ToolOutput))
        assert len(app.query(OutputToolbar)) >= 1
        # the arc reached its terminal finding note
        assert any("overriding the config" in n.message for n in app.query(SystemNote))


@pytest.mark.asyncio
async def test_case_b_turn2_read_chain_structure():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive_case_b(app, pilot)

        chain = app.query_one(ReadChainGroup)
        assert len(chain.nodes()) == 5                     # 5 reads added
        dead = [n for n in chain.nodes() if n.row.status == "stopped"]
        assert len(dead) == 1                              # 1 dead-end backtrack
        assert "dead end" in str(dead[0].row.render())


@pytest.mark.asyncio
async def test_case_b_turn4_tier2_enabled():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive_case_b(app, pilot)

        tier2_outputs = [o for o in app.query(ToolOutput) if o.tier2]
        assert len(tier2_outputs) == 1                     # the CI log only
        assert len(tier2_outputs[0].query(OutputToolbar)) == 1


@pytest.mark.asyncio
async def test_case_b_turn6_reconciliation():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive_case_b(app, pilot)

        block = app.query_one(ReconciliationBlock)
        assert block.kept and block.reverted and block.added


@pytest.mark.asyncio
async def test_pending_redirect_queued_during_turn():
    """Submitting text while a turn worker is running queues it as a pending
    redirect (not a new turn) and drops a 'queued redirect' note."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        app._turn_worker = app.run_worker(app._run_case_b(), exclusive=True)

        # let the turn reach its first HITL — the worker is running, awaiting input
        for _ in range(400):
            await pilot.pause()
            if app.query(FreeText):
                break
        assert app._turn_worker.is_running

        app.on_prompt_area_submitted(PromptArea.Submitted("also check the timeout"))
        for _ in range(400):
            await pilot.pause()
            if app._pending_redirect is not None:
                break

        assert app._pending_redirect == "also check the timeout"
        assert any("queued redirect" in n.message for n in app.query(SystemNote))

        app._turn_worker.cancel()
