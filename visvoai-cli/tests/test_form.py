"""Form HITL tests — multi-field inline form: advance, submit, cancel, newline."""
from __future__ import annotations

import asyncio

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Form
from visvoai.cli.widgets.form import FieldArea, FormField

FIELDS = [("name", "Name", "anthropic"), ("env", "Env var", "KEY")]


@pytest.mark.asyncio
async def test_form_mounts_with_fields_and_focuses_first():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_form("Configure:", FIELDS))
        await pilot.pause()
        form = app.screen.query_one(Form)
        assert len(form.query(FormField)) == 2
        assert form.query(FieldArea).first().has_focus

        form._resolve(None)
        await task


@pytest.mark.asyncio
async def test_enter_advances_then_submits():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_form("Configure:", FIELDS))
        await pilot.pause()
        form = app.screen.query_one(Form)
        fields = list(form.query(FieldArea))

        for ch in "foo":
            await pilot.press(ch)
        await pilot.press("enter")  # advance to field 2
        await pilot.pause()
        assert fields[1].has_focus
        for ch in "bar":
            await pilot.press(ch)
        await pilot.press("enter")  # last field → submit
        await pilot.pause()

        values = await task
        assert values == {"name": "foo", "env": "bar"}


@pytest.mark.asyncio
async def test_ctrl_j_inserts_newline_in_field():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_form("Configure:", FIELDS))
        await pilot.pause()
        form = app.screen.query_one(Form)
        field = form.query(FieldArea).first()
        for ch in "ab":
            await pilot.press(ch)
        await pilot.press("ctrl+j")
        for ch in "cd":
            await pilot.press(ch)
        await pilot.pause()
        assert field.text == "ab\ncd"   # newline, not advance
        assert field.has_focus           # still on field 1

        form._resolve(None)
        await task


@pytest.mark.asyncio
async def test_escape_cancels_form():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.ask_form("Configure:", FIELDS))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        values = await task
        assert values is None


@pytest.mark.asyncio
async def test_form_demo_action_runs():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app.run_action("form_demo"))
        await pilot.pause()
        form = app.screen.query_one(Form)
        assert form is not None
        form._resolve(None)
        await pilot.pause()
        await task


def test_style_race_guard_returns_blank_instead_of_raising():
    """The mount/compositor race (textual#6208): a paint can query component
    styles BEFORE CSS populated the registry — deterministically simulated by
    clearing it. The guard must yield one blank frame, never a KeyError from
    inside a timer callback (which kills the whole app)."""
    from rich.style import Style

    from visvoai.cli.widgets.form import FieldArea
    field = FieldArea("k", "label")
    field._component_styles.clear()          # the race window, made reliable
    style = field.get_component_rich_style("text-area--gutter")
    assert isinstance(style, Style)          # blank, not raised

    from visvoai.cli.widgets.prompt import PromptArea
    prompt = PromptArea()
    prompt._component_styles.clear()
    assert isinstance(prompt.get_component_rich_style("text-area--gutter"), Style)
