"""SystemNote rendering + turn interrupt (esc stops a streaming turn)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Selection, SystemNote, Thinking
from visvoai.cli.widgets.prompt import PromptArea


@pytest.mark.asyncio
async def test_system_note_render_per_kind():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log")
        for kind, glyph in [("stopped", "⊘"), ("compacted", "✦"),
                            ("branch", "◈"), ("zzz", "⊕")]:  # zzz → info fallback; ◈ = milestone (⎇ is git-only)
            note = SystemNote(kind, kind=kind)
            await log.mount(note)
            await pilot.pause()
            assert glyph in str(note.render())


@pytest.mark.asyncio
async def test_esc_interrupts_streaming_turn():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # default pace here: we interrupt mid-stream, so we need the streaming window.
        # Drive the MOCK showcase turn directly (submit now starts a REAL turn);
        # the prompt stays focused so esc routes to the interrupt handler.
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        # Wait for compose (#pinned) before driving the demo turn — _run_turn pins
        # a plan immediately, which races mount otherwise.
        for _ in range(20):
            await pilot.pause()
            if app.query("#pinned"):
                break
        app._turn_worker = app.run_worker(app._run_turn("hi"), exclusive=True)
        for _ in range(200):
            await pilot.pause()
            if app.query(Thinking):
                break
        assert app.query(Thinking)          # mid-turn
        assert not app.query(Selection)     # not yet at the approval HITL

        await pilot.press("escape")         # interrupt
        await pilot.pause()

        stopped = [n for n in app.query(SystemNote) if n.kind == "stopped"]
        assert len(stopped) == 1            # the interrupt dropped a 'stopped' note
        assert app._turn_worker is None
        # killed before the approval HITL was ever reached
        assert not app.query(Selection)


@pytest.mark.asyncio
async def test_esc_when_idle_is_noop():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt", PromptArea).focus()
        await pilot.press("escape")         # nothing running
        await pilot.pause()
        assert not app.query(SystemNote)
