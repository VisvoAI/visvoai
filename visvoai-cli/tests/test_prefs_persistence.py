"""User preferences persist across launches; conversation settings across resumes.

Fix pair for: (1) preferences (theme/model/thinking) lost on relaunch, and
(2) a resumed conversation losing its own model/thinking selection."""
from __future__ import annotations

import pytest

from visvoai.cli import state, store, theme
from visvoai.cli import VisvoApp


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    yield tmp_path


def test_prefs_roundtrip(home):
    assert state.get_pref("theme") is None
    state.set_pref("theme", "visvo-emerald-light")
    state.set_pref("model", "gemini:gemini-3-flash-preview")
    assert state.get_pref("theme") == "visvo-emerald-light"
    assert state.get_pref("model") == "gemini:gemini-3-flash-preview"
    # coexists with the tips/coachmark state in the same file
    state.record_used("rewind")
    assert state.get_pref("theme") == "visvo-emerald-light"


@pytest.mark.asyncio
async def test_saved_theme_applies_on_launch(home):
    state.set_pref("theme", "visvo-emerald-light")
    app = VisvoApp()
    async with app.run_test():
        assert app.theme == "visvo-emerald-light"


@pytest.mark.asyncio
async def test_stale_theme_pref_falls_back(home):
    state.set_pref("theme", "visvo-renamed-away-dark")
    app = VisvoApp()
    async with app.run_test():
        assert app.theme in {t.name for t in theme.THEMES}


@pytest.mark.asyncio
async def test_theme_change_is_saved(home):
    app = VisvoApp()
    async with app.run_test():
        app._apply_theme("visvo-sunset-dark")
    assert state.get_pref("theme") == "visvo-sunset-dark"


def test_resume_adopts_conversation_model(home, monkeypatch):
    """_adopt_conversation_settings: meta model+thinking win when available;
    unavailable model keeps current and notifies."""
    from visvoai.cli import agent as agent_mod
    from visvoai.cli.sessions import SessionsMixin

    class FakeDV:
        thinking_levels = ["low", "high"]

    class Host(SessionsMixin):
        def __init__(self):
            self._model = "current:model"
            self._thinking = None
            self.notes = []
        def notify(self, msg, **kw): self.notes.append(msg)
        def _refresh_model_status(self): pass

    monkeypatch.setattr(agent_mod, "deployment_view",
                        lambda mid: FakeDV() if mid in ("saved:model", "current:model") else None)

    h = Host()
    h._adopt_conversation_settings({"model": "saved:model", "thinking": "high"})
    assert (h._model, h._thinking) == ("saved:model", "high")

    h = Host()
    h._adopt_conversation_settings({"model": "gone:model", "thinking": "high"})
    assert h._model == "current:model"          # kept
    assert h._thinking is None                  # gone-model's thinking NOT adopted
    assert "not available" in h.notes[0]

    h = Host()  # invalid thinking level for the model → ignored
    h._adopt_conversation_settings({"model": "saved:model", "thinking": "ultra"})
    assert (h._model, h._thinking) == ("saved:model", None)


@pytest.mark.asyncio
async def test_context_gauge_visible_at_zero_percent(home):
    """0% used to render muted-on-panel — invisible when panel ≈ terminal bg.
    The empty track now sits on the hover tint, so the gauge always has a body."""
    from visvoai.cli.widgets.status import StatusBar

    app = VisvoApp()
    async with app.run_test() as pilot:
        sb = app.query_one("#status", StatusBar)
        sb.set_context(0, 12)
        await pilot.pause()
        cell = app.query_one("#sb-right")
        rendered = cell.render()
        # every track char carries an explicit background (the hover tint)
        spans = [s for s in rendered.spans if "on " in str(s.style)]
        assert spans, "gauge track has no background styling at 0%"
        assert "0%" in rendered.plain
