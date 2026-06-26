"""Demo-action tests — blocking HITL demos run off the pump (no deadlock) and
respond to Esc. These guard the regression where the choice/form demos froze the
UI. (The demos are no longer user-reachable via key/slash — kept for tests — so
they're driven here through run_command directly.)
"""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Form, Selection
from visvoai.cli.widgets.prompt import PromptArea


@pytest.mark.asyncio
async def test_choice_demo_does_not_freeze_and_esc_cancels():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.run_command("choice")  # the path that used to deadlock
        await pilot.pause()
        assert app.query(Selection)        # mounted, pump not blocked
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query(Selection)    # esc delivered → cancelled
        # app still responsive
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("x")
        await pilot.pause()
        assert p.text == "x"


@pytest.mark.asyncio
async def test_form_demo_does_not_freeze_and_esc_cancels():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.run_command("form")
        await pilot.pause()
        assert app.query(Form)
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query(Form)


@pytest.mark.asyncio
async def test_choice_demo_via_slash_command_also_works():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.run_command("choice")
        await pilot.pause()
        assert app.query(Selection)
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query(Selection)
