"""Truncation + show-more tests for ToolOutput and CleanDiff."""
from __future__ import annotations

import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import CleanDiff, ToolOutput
from visvoai.cli.widgets.diff import DiffLine
from visvoai.cli.widgets.output import OutputLine, ShowMore


@pytest.mark.asyncio
async def test_tool_output_truncates_and_shows_more_control():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = ToolOutput([f"line {i}" for i in range(30)], max_lines=10)
        await log.mount(out)
        await pilot.pause()
        assert len(out.query(OutputLine)) == 10
        more = out.query_one(ShowMore)
        assert more.hidden == 20


@pytest.mark.asyncio
async def test_tool_output_expands_on_show_more():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = ToolOutput([f"line {i}" for i in range(30)], max_lines=10)
        await log.mount(out)
        await pilot.pause()
        out.query_one(ShowMore).post_message(ShowMore.Pressed())
        await pilot.pause()
        assert len(out.query(OutputLine)) == 30
        # expanded → a 'show less' control remains, which collapses it back
        collapse = out.query_one(ShowMore)
        assert collapse.expanded is True
        collapse.post_message(ShowMore.Pressed())
        await pilot.pause()
        assert len(out.query(OutputLine)) == 10
        assert out.query_one(ShowMore).expanded is False


@pytest.mark.asyncio
async def test_short_output_not_truncated():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = ToolOutput(["a", "b", "c"], max_lines=10)
        await log.mount(out)
        await pilot.pause()
        assert len(out.query(OutputLine)) == 3
        assert len(out.query(ShowMore)) == 0


@pytest.mark.asyncio
async def test_clean_diff_truncates_and_expands():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        changes = [("add", f"x{i} = {i}") for i in range(25)]
        diff = CleanDiff("big.py", changes, max_lines=10)
        await log.mount(diff)
        await pilot.pause()
        assert len(diff.query(DiffLine)) == 10
        assert diff.query_one(ShowMore).hidden == 15

        diff.query_one(ShowMore).post_message(ShowMore.Pressed())
        await pilot.pause()
        assert len(diff.query(DiffLine)) == 25
        # expanded → 'show less' control collapses it back to max_lines
        collapse = diff.query_one(ShowMore)
        assert collapse.expanded is True
        collapse.post_message(ShowMore.Pressed())
        await pilot.pause()
        assert len(diff.query(DiffLine)) == 10


@pytest.mark.asyncio
async def test_clean_diff_no_max_lines_renders_all():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        changes = [("add", f"x{i} = {i}") for i in range(25)]
        diff = CleanDiff("big.py", changes)  # no max_lines → no truncation
        await log.mount(diff)
        await pilot.pause()
        assert len(diff.query(DiffLine)) == 25
        assert len(diff.query(ShowMore)) == 0
