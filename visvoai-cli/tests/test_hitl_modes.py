"""Graduated HITL approval modes: the enum and the shift+tab / /mode cycle."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.hitl_modes import HITLMode
from visvoai.cli.widgets import StatusBar


def test_cycle_order_wraps():
    assert HITLMode.NORMAL.next() is HITLMode.AUTO_EDIT
    assert HITLMode.AUTO_EDIT.next() is HITLMode.ACCEPT_ALL
    assert HITLMode.ACCEPT_ALL.next() is HITLMode.NORMAL


def test_auto_approves_matrix():
    assert not HITLMode.NORMAL.auto_approves("edit_file")
    assert HITLMode.AUTO_EDIT.auto_approves("edit_file")
    assert HITLMode.AUTO_EDIT.auto_approves("write_file")
    assert not HITLMode.AUTO_EDIT.auto_approves("run_shell")  # shell stays gated
    assert HITLMode.ACCEPT_ALL.auto_approves("run_shell")


def test_chip_hidden_in_normal():
    assert HITLMode.NORMAL.chip is None
    assert HITLMode.AUTO_EDIT.chip == "auto-edit"
    assert HITLMode.ACCEPT_ALL.chip == "accept-all"


@pytest.mark.asyncio
async def test_shift_tab_routes_and_cycles():
    """shift+tab must reach the App binding — the focused prompt (TextArea) would
    otherwise swallow it (focus-previous), so the binding is priority=True."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._hitl_mode is HITLMode.NORMAL  # session always starts normal
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app._hitl_mode is HITLMode.AUTO_EDIT
        assert app.query_one("#status", StatusBar)._mode == "auto-edit"
        await pilot.press("shift+tab")
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app._hitl_mode is HITLMode.NORMAL  # wraps
        assert app.query_one("#status", StatusBar)._mode is None


@pytest.mark.asyncio
async def test_mode_slash_command_cycles():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.run_command("mode")
        assert app._hitl_mode is HITLMode.AUTO_EDIT
