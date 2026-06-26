"""Selection widget tests — verify the inline HITL prompt works.

CONTINUE.md notes: "Inline selection HITL (Selection widget): arrow-nav, Recommended tag,
notes, esc"
"""
from __future__ import annotations

import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp


async def _mount_selection(app, prompt: str, options: list[str], recommended: int = 0):
    """Helper: mount a Selection via the app's ask_choice helper, return the future."""
    return await app.ask_choice(prompt, options, recommended=recommended)


@pytest.mark.asyncio
async def test_selection_mounts_and_focuses():
    """Selection mounts, takes focus, shows options + recommended tag + hint."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B", "C"], recommended=0
        ))
        await pilot.pause()
        from visvoai.cli.widgets import Selection
        sel = app.screen.query_one(Selection)
        assert sel.has_focus
        # Three OptionRows mounted
        rows = sel.query("OptionRow")
        assert len(rows) == 3
        # Recommended tag visible on the first row (OptionRow renders itself).
        rendered_first = str(rows[0].render())
        assert "(recommended)" in rendered_first
        # Hint bar present
        assert sel.query(".sel-hint")
        # Resolve so the test cleans up
        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_selection_arrow_keys_change_active_row():
    """↑/↓ moves the active option; the active row has the ❯ marker."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B", "C"], recommended=0
        ))
        await pilot.pause()
        from visvoai.cli.widgets import Selection
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        # Initial active = 0
        assert sel.idx == 0
        await pilot.press("down")
        await pilot.pause()
        assert sel.idx == 1
        await pilot.press("down")
        await pilot.pause()
        assert sel.idx == 2
        await pilot.press("down")  # wrap
        await pilot.pause()
        assert sel.idx == 0
        await pilot.press("up")  # wrap
        await pilot.pause()
        assert sel.idx == 2

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_selection_enter_resolves_with_index():
    """Pressing enter while a selection is active resolves the future with (idx, note)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        from visvoai.cli.widgets import Selection
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()
        await pilot.press("down")  # pick B
        await pilot.press("enter")
        await pilot.pause()
        idx, note = await task
        assert idx == 1
        assert note == ""


@pytest.mark.asyncio
async def test_selection_escape_resolves_with_none():
    """Esc cancels — returns (None, note)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        from visvoai.cli.widgets import Selection
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        idx, note = await task
        assert idx is None


# Imported late to keep top-of-file clean
import asyncio

@pytest.mark.asyncio
async def test_options_are_numbered():
    """Each option row shows a 1-based number; the active row leads with ❯."""
    from visvoai.cli.widgets.selection import OptionRow, Selection

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        sel = Selection("Pick one", ["alpha", "beta", "gamma"])
        await app.query_one("#log").mount(sel)
        await pilot.pause()
        rows = sel.query(OptionRow)
        assert "1. alpha" in str(rows[0].render())
        assert "2. beta" in str(rows[1].render())
        assert "❯" in str(rows[0].render())       # active (idx 0) leads with the marker
        assert "❯" not in str(rows[1].render())    # inactive: no marker


@pytest.mark.asyncio
async def test_digit_key_selects_option():
    """Pressing a digit resolves to that option directly."""
    from visvoai.cli.widgets.selection import Selection

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        sel = Selection("Pick one", ["alpha", "beta", "gamma"])
        await app.query_one("#log").mount(sel)
        await pilot.pause()
        fut = sel.ask()
        sel.focus()
        await pilot.press("2")
        idx, _ = await fut
        assert idx == 1                            # "2" → second option (index 1)
