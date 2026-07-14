"""Thinking persistence — the thought block stays visible after the answer."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Assistant, Selection, Thinking
from visvoai.cli.widgets.prompt import PromptArea


async def _run_turn_to_selection(app, pilot):
    # Drive the MOCK showcase turn directly. Submit (enter) now starts a REAL
    # agent turn (integration Phase 1); the mock turn — which renders the Thinking
    # block + the Selection HITL these tests assert on — is invoked via its worker,
    # the same way the _run_case_* tests drive their arcs.
    app._pace = 0.04  # run the demo fast in tests
    # Wait for the app to finish composing (#pinned exists) before driving the
    # demo turn — _run_turn pins a plan immediately, which races mount otherwise.
    # Unbounded-ish with a REAL clock (CI runners can take >20 ticks to
    # compose) and loud on failure — silently proceeding is how this raced.
    import asyncio
    for _ in range(200):
        await pilot.pause()
        if app.query("#pinned") and app.query("#log"):
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("app never finished composing (#pinned/#log missing)")
    app._turn_worker = app.run_worker(app._run_turn("hi"), exclusive=True)
    for _ in range(400):
        await pilot.pause()
        if app.query(Selection):
            return


@pytest.mark.asyncio
async def test_thinking_persists_after_answer_streams():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _run_turn_to_selection(app, pilot)

        thinks = app.query(Thinking)
        assert len(thinks) == 1               # NOT removed when answer started
        t = thinks.first()
        assert t._active is False             # spinner stopped (done state)
        assert t._buf                          # thinking text retained
        assert len(app.query(Assistant)) >= 1  # answer is a separate block

        app.query(Selection).first()._resolve((0, ""))
        await pilot.pause()


@pytest.mark.asyncio
async def test_thinking_collapsed_by_default_with_duration():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _run_turn_to_selection(app, pilot)
        t = app.query(Thinking).first()
        rendered = str(t.render())
        assert "Thought for" in rendered      # summary with duration (Title case)
        assert "Thinking…" not in rendered
        assert t._expanded is False
        # collapsed → reasoning text NOT in the rendered output
        assert t._buf.split(" ")[0] not in rendered

        app.query(Selection).first()._resolve((0, ""))
        await pilot.pause()


@pytest.mark.asyncio
async def test_thinking_expands_on_click():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _run_turn_to_selection(app, pilot)
        t = app.query(Thinking).first()
        t.on_click()                          # expand
        await pilot.pause()
        assert t._expanded is True
        assert t._buf[:10] in str(t.render())  # reasoning now visible
        t.on_click()                          # collapse again
        await pilot.pause()
        assert t._expanded is False

        app.query(Selection).first()._resolve((0, ""))
        await pilot.pause()


@pytest.mark.asyncio
async def test_thinking_not_expandable_while_active():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from visvoai.cli.widgets import Thinking as T
        log = app.query_one("#log")
        t = T()
        await log.mount(t)
        await pilot.pause()
        assert t._active is True
        t.on_click()                          # ignored while thinking
        assert t._expanded is False
        t.stop()
