"""End-to-end: each Wave-2 case arc (A/C/E/F/G) runs to completion through its
HITLs, and the foundations it exists to exercise actually render.

A generic driver resolves any FreeText (canned answers) and any Selection (option
0) until the arc's terminal SystemNote appears, then asserts on the persistent log
widgets that prove the case's foundations fired."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import (
    Citation, FileCreation, FreeText, ReconciliationBlock,
    Selection, SeverityOutput, StructureTree, SystemNote,
)
from visvoai.cli.widgets.system_note import CompactionMarker
from visvoai.cli.widgets import ToolRow


async def _drive(app, pilot, coro_factory, terminal: str,
                 ft_answers: list[str] | None = None, max_iters: int = 20000) -> None:
    """Run an arc to its terminal note, resolving HITLs as they appear."""
    ft_answers = ft_answers or ["keyset on id, ascending"]
    worker = app.run_worker(coro_factory(), exclusive=True)
    app._turn_worker = worker
    ai = 0
    for _ in range(max_iters):
        await pilot.pause()
        fts = app.query(FreeText)
        if fts:
            fts.first()._resolve(ft_answers[min(ai, len(ft_answers) - 1)])
            ai += 1
            continue
        sels = app.query(Selection)
        if sels:
            sels.first()._resolve((0, ""))   # take the first option
            continue
        if any(terminal in n.message for n in app.query(SystemNote)):
            await worker.wait()
            return
    raise AssertionError(f"arc never reached terminal note: {terminal!r}")


def _tags(app) -> list[str]:
    return [r.tag for r in app.query(ToolRow) if r.tag]


@pytest.mark.asyncio
async def test_case_a_refactor_arc():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive(app, pilot, app._run_case_a, "refactor complete")
        # auto-apply pattern fired, stale-read surfaced, compaction happened
        assert "auto-applied" in _tags(app)
        assert any(n.kind == "stale" for n in app.query(SystemNote))
        assert len(app.query(CompactionMarker)) == 1


@pytest.mark.asyncio
async def test_case_c_redirection_arc():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive(app, pilot, app._run_case_c, "cursor pagination shipped")
        # the mid-task redirect produced a reconciliation block
        assert len(app.query(ReconciliationBlock)) == 1


@pytest.mark.asyncio
async def test_case_e_incident_arc():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive(app, pilot, app._run_case_e, "cherry-pick it")
        # the diagnosis is now a prose reply (no orphaned error block);
        # cross-branch reminder present
        assert any("hotfix/inc-2241" in n.message and "NOT on main" in n.message
                   for n in app.query(SystemNote))


@pytest.mark.asyncio
async def test_case_f_greenfield_arc():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive(app, pilot, app._run_case_f, "scaffold ready")
        assert len(app.query(StructureTree)) == 1
        assert len(app.query(FileCreation)) == 6   # the scaffold batch


@pytest.mark.asyncio
async def test_case_g_upgrade_arc():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        await _drive(app, pilot, app._run_case_g, "upgrade complete")
        assert len(app.query(Citation)) == 1
        assert len(app.query(SeverityOutput)) == 1
        assert "pattern-applied" in _tags(app)
