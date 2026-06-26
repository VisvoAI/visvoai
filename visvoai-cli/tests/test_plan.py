"""Plan — live task tracker (start/complete/header/stop)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Plan
from visvoai.cli.widgets.plan import PlanStep
from visvoai.cli.widgets.prompt import PromptArea


async def _mount(app, pilot) -> Plan:
    p = Plan(["one", "two", "three"])
    await app.query_one("#log").mount(p)
    await pilot.pause()
    return p


@pytest.mark.asyncio
async def test_plan_states_and_header():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = await _mount(app, pilot)
        steps = p.query(PlanStep)
        assert all(s.state == "pending" for s in steps)
        assert "0/3" in str(p.query_one(".plan-header").render())

        p.start(0)
        assert steps[0].state == "active"
        p.complete(0)
        p.start(1)
        await pilot.pause()
        assert steps[0].state == "done"
        assert steps[1].state == "active"
        assert "1/3" in str(p.query_one(".plan-header").render())

        # done step renders a ✓; active renders a spinner frame
        assert "✓" in str(steps[0].render())
        assert any(f in str(steps[1].render()) for f in PlanStep.SPINNER)


@pytest.mark.asyncio
async def test_pinned_plan_suppressed_by_slash_menu():
    """Above-input priority: slash menu (2) hides the pinned plan (3)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await app._pin_plan(Plan(["a", "b"]))
        await pilot.pause()
        pinned = app.query_one("#pinned")
        assert pinned.display is True

        app.query_one("#prompt", PromptArea).focus()
        await pilot.press("/")
        await pilot.pause()
        assert pinned.display is False        # slash open → plan hidden

        await pilot.press("backspace")        # closes the slash menu
        await pilot.pause()
        assert pinned.display is True         # restored


@pytest.mark.asyncio
async def test_pinned_plan_suppressed_during_hitl():
    """Above-input priority: an active HITL (1) hides the pinned plan (3)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await app._pin_plan(Plan(["a"]))
        await pilot.pause()
        pinned = app.query_one("#pinned")
        assert pinned.display is True
        with app._hidden_prompt():
            assert pinned.display is False    # HITL active → plan hidden
        assert pinned.display is True         # restored after


@pytest.mark.asyncio
async def test_plan_insert_step():
    """Agent discovers a missed site → inserts a step mid-plan; total grows."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = await _mount(app, pilot)
        assert "0/3" in str(p.query_one(".plan-header").render())
        await p.insert(1, "re-scan for missed sites")
        await pilot.pause()
        labels = [s.label for s in p.query(PlanStep)]
        assert labels == ["one", "re-scan for missed sites", "two", "three"]
        assert "0/4" in str(p.query_one(".plan-header").render())


@pytest.mark.asyncio
async def test_plan_abandon_step():
    """Abandoned steps are struck, glyph ⊘, and leave the denominator."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = await _mount(app, pilot)
        steps = p.query(PlanStep)
        p.complete(0)
        p.abandon(2)
        await pilot.pause()
        assert steps[2].state == "abandoned"
        assert "⊘" in str(steps[2].render())
        assert "abandoned" in str(steps[2].render())
        # 1 done, 1 abandoned → 1 of the 2 remaining
        assert "1/2" in str(p.query_one(".plan-header").render())


@pytest.mark.asyncio
async def test_plan_supersede_with_replacement():
    """Supersede marks a done step undone and inserts its replacement after it."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = await _mount(app, pilot)
        p.complete(0)
        await p.supersede(0, replacement="redo it the new way")
        await pilot.pause()
        steps = p.query(PlanStep)
        assert steps[0].state == "superseded"
        assert "↻" in str(steps[0].render())
        assert steps[1].label == "redo it the new way"
        assert steps[1].state == "pending"
        # superseded leaves the denominator: 0 done of (4 - 1) = 3
        assert "0/3" in str(p.query_one(".plan-header").render())


@pytest.mark.asyncio
async def test_plan_dependency_hint_appears_then_clears():
    """A step with depends_on shows 'after «dep»' until the prereq completes."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # step 1 (route) depends on step 0 (model)
        p = Plan(["build model", "build route"], deps={1: 0})
        await app.query_one("#log").mount(p)
        await pilot.pause()
        steps = p.query(PlanStep)
        assert "after" in str(steps[1].render())
        assert "build model" in str(steps[1].render())
        p.complete(0)
        await pilot.pause()
        # prerequisite done → hint clears
        assert "after" not in str(steps[1].render())


@pytest.mark.asyncio
async def test_plan_insert_reindexes_dependency():
    """Inserting before a dependent shifts its prerequisite index so the hint
    still points at the right step."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = Plan(["model", "route"], deps={1: 0})
        await app.query_one("#log").mount(p)
        await pilot.pause()
        await p.insert(0, "scaffold dirs")  # pushes model→1, route→2
        await pilot.pause()
        steps = p.query(PlanStep)
        assert [s.label for s in steps] == ["scaffold dirs", "model", "route"]
        # route still depends on model (now at index 1)
        assert steps[2].depends_on == 1
        assert "model" in str(steps[2].render())


@pytest.mark.asyncio
async def test_plan_stop_halts_spinner():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = await _mount(app, pilot)
        p.start(0)
        p.stop()
        assert p._timer is None      # interval halted (e.g. on interrupt)
