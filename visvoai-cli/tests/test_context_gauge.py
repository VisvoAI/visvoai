"""Context-usage gauge in the StatusBar + /compact reclaiming it."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import CompactionMarker, StatusBar


def _right(app) -> str:
    return str(app.query_one("#status", StatusBar).query_one("#sb-right").render())


@pytest.mark.asyncio
async def test_gauge_hidden_at_startup():
    """No usage yet: the gauge stays hidden until a real turn reports token usage."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._ctx_pct is None
        assert "%" not in _right(app)
        # once a turn reports usage, the gauge appears with the token count as label
        app._set_context(42, 12_500)
        await pilot.pause()
        right = _right(app)
        assert "42%" in right and "12.5K tokens" in right
        # the word "Context" is intentionally gone — the count replaces it
        assert "Context" not in right


@pytest.mark.asyncio
async def test_gauge_resets_on_clear():
    """/clear starts a fresh conversation: the gauge + cost must clear, not linger."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._set_context(60, 80_000)
        app._conv_cost = 0.5
        app._update_cost_status()
        await pilot.pause()
        assert "60%" in _right(app)
        await app._clear_log()
        await pilot.pause()
        assert app._ctx_pct is None and app._ctx_tokens is None
        right = _right(app)
        assert "%" not in right and "$" not in right
        # conversation thread reset too — next turn won't continue the old one
        assert app._history == [] and app._conv_id is None


@pytest.mark.asyncio
async def test_gauge_hidden_when_none():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one("#status", StatusBar)
        bar.set_context(None)
        await pilot.pause()
        assert "context" not in _right(app)


@pytest.mark.asyncio
async def test_compact_resets_gauge_and_marks():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.run_command("compact")
        for _ in range(20):
            await pilot.pause()
            if app.query(CompactionMarker):
                break
        marker = app.query(CompactionMarker).first()
        assert "context compacted" in str(marker.render())
        assert "— → 14%" in str(marker.render())   # before unknown (no turn yet) → after
        assert app._ctx_pct == 14
        assert "14%" in _right(app)


@pytest.mark.asyncio
async def test_context_warning_floats_above_input_near_limit():
    """A nudge appears above the input when context is nearly full, and clears
    once there's headroom."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._set_context(50)
        await pilot.pause()
        assert not app.query("#ctx-warning")
        app._set_context(90)
        await pilot.pause()
        warn = app.query("#ctx-warning")
        assert warn and "compact" in str(warn.first().render()).lower()
        app._set_context(30)
        await pilot.pause()
        assert not app.query("#ctx-warning")
