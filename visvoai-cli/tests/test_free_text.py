"""FreeText HITL tests — free-form clarification ask: focus, submit, empty-noop,
cancel, unmount. Mirrors test_selection.py / test_form.py."""
from __future__ import annotations

import asyncio

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import FreeText
from visvoai.cli.widgets.form import FieldArea


@pytest.mark.asyncio
async def test_free_text_mounts_and_focuses():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_text("Which run?", "paste it…"))
        await pilot.pause()
        ft = app.screen.query_one(FreeText)
        assert ft.query(FieldArea).first().has_focus
        assert ft.query(".ft-prompt")
        assert ft.query(".ft-hint")

        ft._resolve(None)
        await task


@pytest.mark.asyncio
async def test_free_text_submit_resolves_text():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_text("Which run?"))
        await pilot.pause()
        for ch in "tuesday":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        result = await task
        assert result == "tuesday"


@pytest.mark.asyncio
async def test_free_text_empty_submit_is_noop():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_text("Which run?"))
        await pilot.pause()
        ft = app.screen.query_one(FreeText)
        await pilot.press("enter")  # empty → no-op
        await pilot.pause()
        assert not ft._future.done()

        ft._resolve(None)
        await task


@pytest.mark.asyncio
async def test_free_text_esc_cancels():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_text("Which run?"))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        result = await task
        assert result is None


@pytest.mark.asyncio
async def test_free_text_unmount_resolves_none():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_text("Which run?"))
        await pilot.pause()
        ft = app.screen.query_one(FreeText)
        await ft.remove()  # unmount mid-prompt → no dangling future
        await pilot.pause()
        result = await task
        assert result is None
