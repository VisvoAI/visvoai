"""Scroll tests — verify PageUp/PgDn/mouse-wheel scroll the conversation log.

CONTINUE.md notes (open bug, headless): "Manual scroll-back not working. PageUp/PageDown
bindings + mouse wheel are wired (action_scroll_up/down → scroll_page_up/down on #log),
but the user reports it doesn't scroll back. Could be: binding not firing, focus routing,
or terminal alt-screen scroll behavior."

These tests verify the bindings fire and scroll position changes. Terminal-side scroll
behavior (iTerm2 / etc.) is out of scope; we verify the app does the right thing.
"""
from __future__ import annotations

import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp


async def _fill_log_with_turns(app, n: int) -> None:
    """Mount n UserMsg blocks so the log is scrollable."""
    from visvoai.cli.widgets import UserMsg
    log = app.screen.query_one("#log", VerticalScroll)
    for i in range(n):
        await log.mount(UserMsg(f"turn {i}"))
    # Force layout + scroll. In Textual 8.x scroll_end is sync; use immediate=True
    # to skip the animation queue.
    log.scroll_end(animate=False, immediate=True)


@pytest.mark.asyncio
async def test_pageup_binding_is_registered():
    """The app must expose PageUp → action_scroll_up binding."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        binding_keys = {b.key for b in app.BINDINGS}
        assert "pageup" in binding_keys
        assert "pagedown" in binding_keys


@pytest.mark.asyncio
async def test_pageup_scrolls_log_back_when_log_is_focused():
    """When #log is focused and has overflow, PageUp moves the scroll position back."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _fill_log_with_turns(app, 60)
        await pilot.pause()

        log = app.screen.query_one("#log", VerticalScroll)
        log.focus()
        await pilot.pause()

        # Get scroll position after mount (likely at end)
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        at_end = log.scroll_offset

        # PageUp — must decrease scroll_offset.y (move up the document)
        await pilot.press("pageup")
        await pilot.pause()
        after_pageup = log.scroll_offset

        assert after_pageup.y < at_end.y, (
            f"PageUp did not move scroll: end={at_end.y}, after={after_pageup.y}"
        )


@pytest.mark.asyncio
async def test_pagedown_scrolls_log_forward():
    """PageDown moves scroll position forward (toward end of document)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _fill_log_with_turns(app, 60)
        await pilot.pause()

        log = app.screen.query_one("#log", VerticalScroll)
        log.focus()
        await pilot.pause()
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        log.scroll_page_up()
        await pilot.pause()
        before = log.scroll_offset

        await pilot.press("pagedown")
        await pilot.pause()
        after = log.scroll_offset

        assert after.y > before.y, (
            f"PageDown did not move scroll forward: before={before.y}, after={after.y}"
        )


@pytest.mark.asyncio
async def test_pageup_works_when_prompt_is_focused():
    """REGRESSION GUARD: when the input is focused (the default), PageUp must still
    scroll the log. The default focus is the prompt — if bindings don't take priority,
    PageUp falls through to the input and the user can't scroll back."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _fill_log_with_turns(app, 60)
        await pilot.pause()

        log = app.screen.query_one("#log", VerticalScroll)
        # Re-focus the prompt (on_mount does this; do it again to be sure)
        app.screen.query_one("#prompt").focus()
        await pilot.pause()
        log.scroll_end(animate=False, immediate=True)
        await pilot.pause()
        before = log.scroll_offset

        await pilot.press("pageup")
        await pilot.pause()
        after = log.scroll_offset

        assert after.y < before.y, (
            f"PageUp did not scroll when prompt was focused: before={before.y}, after={after.y}"
        )