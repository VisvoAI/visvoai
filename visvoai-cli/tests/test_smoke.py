"""Smoke tests — verify the app launches and the expected top-level structure is present.

These are pure structural assertions. No pixel checks.
"""
from __future__ import annotations

import pytest

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header

from visvoai.cli import VisvoApp
from visvoai.cli.widgets.prompt import PromptArea


@pytest.mark.asyncio
async def test_app_launches():
    """App launches without error and reaches a stable mounted state."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.size.width > 0
        assert app.size.height > 0


@pytest.mark.asyncio
async def test_top_level_widgets_present():
    """The screen contains VerticalScroll(#log) and Vertical(#bottom) with the
    prompt + a StatusBar (no top Header / shortcut Footer)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        kinds = [type(w).__name__ for w in app.screen.children]
        assert "Header" not in kinds
        assert "Footer" not in kinds
        # The log lives inside the #main-split Horizontal (agent side panel split).
        assert "Horizontal" in kinds
        assert "Vertical" in kinds
        assert app.screen.query_one("#log") is not None
        bottom = app.screen.query_one("#bottom", Vertical)
        prompt = bottom.query_one("#prompt", PromptArea)
        assert "@mention a file" in prompt.placeholder   # action-oriented dev placeholder
        # status bar lives at the bottom and carries the context info
        from visvoai.cli.widgets import StatusBar
        from textual.widgets import Static
        status = bottom.query_one("#status", StatusBar)
        from visvoai.cli import agent
        # Footer shows the friendly display name (not the raw deployment id).
        dv = agent.deployment_view(agent.default_chat_model())
        assert dv.display_name in str(status.query_one("#sb-left", Static).render())


@pytest.mark.asyncio
async def test_log_widget_present_and_welcome_mounted():
    """#log exists and has the two-column WelcomeBanner with the brand name."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        from visvoai.cli.widgets import WelcomeBanner
        from textual.widgets import Static
        banner = log.query_one(WelcomeBanner)
        assert banner is not None
        left = str(banner.query_one("#wb-left", Static).render())
        assert "terminal coding agent" in left  # tagline under the pixel logo