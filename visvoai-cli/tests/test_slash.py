"""Slash command menu tests — open/filter/navigate/run, plus chromeless note."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Selection, Welcome
from visvoai.cli.widgets.prompt import PromptArea
from visvoai.cli.widgets.slash import SlashCommand, SlashMenu


@pytest.mark.asyncio
async def test_slash_opens_menu_and_sets_active():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("/")
        await pilot.pause()
        assert app.query(SlashMenu)
        assert p.slash_active is True
        from visvoai.cli.commands import SLASH_COMMANDS
        assert len(app.query(SlashCommand)) == len(SLASH_COMMANDS)


@pytest.mark.asyncio
async def test_typing_filters_commands():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt", PromptArea).focus()
        for ch in "/th":
            await pilot.press(ch)
        await pilot.pause()
        names = [r.cmd for r in app.query(SlashCommand)]
        assert names == ["theme"]


@pytest.mark.asyncio
async def test_no_match_shows_empty_state():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt", PromptArea).focus()
        for ch in "/zzz":
            await pilot.press(ch)
        await pilot.pause()
        assert len(app.query(SlashCommand)) == 0
        assert app.query(SlashMenu)  # menu still present, just empty


@pytest.mark.asyncio
async def test_arrow_navigates_and_enter_runs_command():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("/")
        await pilot.pause()
        menu = app.query(SlashMenu).first()
        assert menu.selected() == "help"
        await pilot.press("down")
        await pilot.pause()
        assert menu.selected() == "model"
        await pilot.press("enter")
        # /model ran → the model page opened, menu closed, prompt cleared
        from visvoai.cli.screens import ModelScreen
        for _ in range(40):
            await pilot.pause()
            if isinstance(app.screen, ModelScreen):
                break
        assert isinstance(app.screen, ModelScreen)
        assert not app.query(SlashMenu)
        assert p.text == ""
        assert p.slash_active is False
        app.screen.action_back()  # cancel the page
        await pilot.pause()


@pytest.mark.asyncio
async def test_tab_autocompletes_without_running():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("down")  # highlight "model"
        await pilot.pause()
        await pilot.press("tab")   # autocomplete, must NOT run
        await pilot.pause()
        from visvoai.cli.screens import ModelScreen
        assert p.text == "/model"                        # filled in
        assert not isinstance(app.screen, ModelScreen)   # did NOT execute (no page yet)
        assert app.query(SlashMenu)                      # menu still open
        # now enter runs it → the model page opens
        await pilot.press("enter")
        for _ in range(40):
            await pilot.pause()
            if isinstance(app.screen, ModelScreen):
                break
        assert isinstance(app.screen, ModelScreen)
        app.screen.action_back()
        await pilot.pause()


@pytest.mark.asyncio
async def test_escape_closes_menu_without_running():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query(SlashMenu)
        assert p.slash_active is False
        assert not app.query(Selection)  # nothing ran


@pytest.mark.asyncio
async def test_clearing_slash_hides_menu():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        await pilot.press("/")
        await pilot.pause()
        assert app.query(SlashMenu)
        await pilot.press("backspace")
        await pilot.pause()
        assert not app.query(SlashMenu)
        assert p.slash_active is False


@pytest.mark.asyncio
async def test_prompt_position_stable_when_menu_opens_and_closes():
    """The prompt must not shift when the slash menu is shown then dismissed."""
    app = VisvoApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        y0 = p.region.y
        await pilot.press("/")
        await pilot.pause()
        assert p.region.y == y0       # stable while open (docked bottom)
        await pilot.press("escape")
        await pilot.pause()
        assert p.region.y == y0       # restored after close (no upward jump)


@pytest.mark.asyncio
async def test_clear_command_resets_log_to_welcome():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("error_demo")  # add content
        await pilot.pause()
        from visvoai.cli.widgets import ErrorBlock, WelcomeBanner
        log = app.query_one("#log")
        assert log.query(ErrorBlock)
        app.run_command("clear")
        await pilot.pause()
        assert not log.query(ErrorBlock)
        assert log.query(WelcomeBanner)
