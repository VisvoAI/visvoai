"""Context-usage gauge in the StatusBar + /compact reclaiming it."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, agent, store
from visvoai.cli.widgets import CompactionMarker, StatusBar


async def _async(v):
    return v


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
        # gauge hidden → no percentage/token label in the right cell. (Match the
        # gauge indicator, not the bare word "context" — that collided with branch
        # names like "feat/cli-context-engineering" in the status location.)
        right = _right(app)
        assert "%" not in right and "tokens" not in right


@pytest.mark.asyncio
async def test_compact_folds_history_marks_and_sets_real_gauge(tmp_path, monkeypatch):
    """Real /compact: with enough history + a summary, it folds, marks, and sets a
    real (measured, non-None) gauge — not a hardcoded value."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    monkeypatch.setattr(agent, "summarize_history", lambda *a, **k: _async("SUMMARY"))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        store.ensure_branch(app._project_id, app._conv_id, "main")
        for i in range(1, 5):
            app._history += [HumanMessage(content=f"q{i}"), AIMessage(content=f"a{i}")]
        store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)

        app.run_command("compact")
        for _ in range(20):
            await pilot.pause()
            if app.query(CompactionMarker):
                break
        marker = app.query(CompactionMarker).first()
        assert "context compacted" in str(marker.render())
        assert "folded into a summary" in str(marker.render())
        assert app._ctx_pct is not None                # real, measured — not a mock 14


@pytest.mark.asyncio
async def test_compact_is_a_noop_without_enough_history():
    """Too little to fold → no marker, gauge untouched (honest no-op, not a fake reset)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._history = [HumanMessage(content="q1"), AIMessage(content="a1")]
        app.run_command("compact")
        for _ in range(10):
            await pilot.pause()
        assert not app.query(CompactionMarker)
        assert app._ctx_pct is None


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
