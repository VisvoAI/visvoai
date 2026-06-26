"""ErrorBlock tests — clean inline errors mount and render without tracebacks."""
from __future__ import annotations

import io

import pytest

from rich.console import Console
from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import ErrorBlock


def _render(widget) -> str:
    buf = io.StringIO()
    Console(file=buf, force_terminal=False, width=120).print(widget.render())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_error_block_mounts_with_message_and_detail():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        await log.mount(ErrorBlock("tool", "boom happened", "extra context"))
        await pilot.pause()
        block = log.query_one(ErrorBlock)
        text = _render(block)
        assert "boom happened" in text
        assert "extra context" in text


@pytest.mark.asyncio
async def test_error_block_kind_renders_headline():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        await log.mount(ErrorBlock("model", "model failed"))
        await pilot.pause()
        block = log.query_one(ErrorBlock)
        assert "model error" in str(block.render())  # headline rendered inline


@pytest.mark.asyncio
async def test_error_demo_action_mounts_two_errors():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.run_action("error_demo")
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        assert len(log.query(ErrorBlock)) == 2
