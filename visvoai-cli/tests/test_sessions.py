"""SessionsScreen — full-screen searchable resume picker + /model picker."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.mock import MODELS, SESSIONS
from visvoai.cli.screens import SessionsScreen
from visvoai.cli.screens.sessions import SessionRow
from visvoai.cli.widgets import Selection, StatusBar
from visvoai.cli.widgets.prompt import PromptArea


async def _open_sessions(app, pilot) -> SessionsScreen:
    # Push the screen with mock data directly — these are SessionsScreen WIDGET
    # tests. The app's /resume now lists the real conversation store (integration,
    # covered by test_store.py), which is empty in the test env.
    app.push_screen(SessionsScreen(SESSIONS))
    for _ in range(40):
        await pilot.pause()
        if isinstance(app.screen, SessionsScreen):
            return app.screen
    raise AssertionError("sessions screen never opened")


@pytest.mark.asyncio
async def test_sessions_screen_lists_all_then_filters():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_sessions(app, pilot)
        assert len(screen.query(SessionRow)) == len(SESSIONS)

        # type a query that matches a subset of titles
        for ch in "test":
            await pilot.press(ch)
        await pilot.pause()
        rows = screen.query(SessionRow)
        assert 0 < len(rows) < len(SESSIONS)
        assert all("test" in r.session["title"].lower() for r in rows)


@pytest.mark.asyncio
async def test_sessions_search_no_match_shows_empty():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_sessions(app, pilot)
        for ch in "zzqqx":
            await pilot.press(ch)
        await pilot.pause()
        assert len(screen.query(SessionRow)) == 0
        assert screen.query("#sessions-empty")


@pytest.mark.asyncio
async def test_sessions_navigate_and_resume_dismisses_with_id():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_sessions(app, pilot)
        await pilot.press("down")          # move to 2nd session
        await pilot.pause()
        assert screen.idx == 1
        await pilot.press("enter")         # resume highlighted
        await pilot.pause()
        assert not isinstance(app.screen, SessionsScreen)  # popped


@pytest.mark.asyncio
async def test_sessions_esc_closes_without_choosing():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_sessions(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SessionsScreen)


@pytest.mark.asyncio
async def test_model_picker_changes_status_bar():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from visvoai.cli import agent
        from visvoai.cli.screens import ModelScreen
        assert app._model == agent.default_chat_model()
        app.run_worker(app._model_picker_flow())
        for _ in range(40):
            await pilot.pause()
            if isinstance(app.screen, ModelScreen):
                break
        screen = app.screen
        # Pick a model different from the current one (highlight it in the OptionList).
        from textual.widgets import OptionList
        ol = screen.query_one("#model-list", OptionList)
        target_id = None
        for i in range(ol.option_count):
            oid = ol.get_option_at_index(i).id
            if oid is not None and oid != app._model:
                target_id, ol.highlighted = oid, i
                break
        await screen.action_confirm()
        await pilot.pause()
        # A thinking-capable model opens the level chooser → confirm the default too.
        if isinstance(app.screen, ModelScreen) and app.screen._phase == "think":
            await app.screen.action_confirm()
            await pilot.pause()
        assert app._model == target_id
        bar = app.query_one("#status", StatusBar)
        # Footer shows the new model's friendly name.
        dv = agent.deployment_view(target_id)
        assert dv.display_name in str(bar.query_one("#sb-left").render())
