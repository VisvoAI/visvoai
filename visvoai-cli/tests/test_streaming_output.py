"""StreamingOutput tests — live tail while streaming, freeze on finalize, and
the _run_long_shell helper incl. the core interrupt-keep-partial acceptance test.
"""
from __future__ import annotations

import asyncio

import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import StreamingOutput, SystemNote, ToolNode
from visvoai.cli.widgets.output import OutputLine, ShowMore


@pytest.mark.asyncio
async def test_streaming_output_mounts_empty():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = StreamingOutput(max_lines=12)
        await log.mount(out)
        await pilot.pause()
        assert len(out.query(OutputLine)) == 0
        assert len(out.query(ShowMore)) == 0


@pytest.mark.asyncio
async def test_streaming_output_add_line_grows_tail():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = StreamingOutput(max_lines=12)
        await log.mount(out)
        await pilot.pause()
        for i in range(3):
            out.add_line(f"line {i}")
        await pilot.pause()
        assert len(out.query(OutputLine)) == 3
        assert len(out.query(ShowMore)) == 0
        assert out.lines() == ["line 0", "line 1", "line 2"]


@pytest.mark.asyncio
async def test_streaming_output_truncates_to_tail_while_streaming():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = StreamingOutput(max_lines=12)
        await log.mount(out)
        await pilot.pause()
        for i in range(20):
            out.add_line(f"line {i}")
        await pilot.pause()
        # only the last 12 lines are visible (the live tail)
        assert len(out.query(OutputLine)) == 12
        sm = out.query_one(ShowMore)
        assert sm.streaming is True
        assert sm.hidden == 20  # 'stream truncated, 20 total'
        assert len(out.lines()) == 20


@pytest.mark.asyncio
async def test_streaming_output_finalize_enables_expand():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = StreamingOutput(max_lines=12)
        await log.mount(out)
        await pilot.pause()
        for i in range(20):
            out.add_line(f"line {i}")
        await pilot.pause()
        out.finalize()
        await pilot.pause()
        # now it behaves like ToolOutput: head + normal 'show N more'
        assert len(out.query(OutputLine)) == 12
        sm = out.query_one(ShowMore)
        assert sm.streaming is False
        assert sm.hidden == 8
        # expand → full buffer visible
        sm.post_message(ShowMore.Pressed())
        await pilot.pause()
        assert len(out.query(OutputLine)) == 20
        assert out.query_one(ShowMore).expanded is True


@pytest.mark.asyncio
async def test_streaming_output_expand_while_streaming_is_noop():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        out = StreamingOutput(max_lines=12)
        await log.mount(out)
        await pilot.pause()
        for i in range(20):
            out.add_line(f"line {i}")
        await pilot.pause()
        # the streaming ShowMore is inert — pressing it does not expand
        sm = out.query_one(ShowMore)
        sm.on_click()
        await pilot.pause()
        assert len(out.query(OutputLine)) == 12  # still the tail, not expanded


@pytest.mark.asyncio
async def test_run_long_shell_streams_to_completion():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        log = app.screen.query_one("#log", VerticalScroll)

        async def gen():
            for i in range(5):
                yield f"out {i}"

        worker = app.run_worker(app._run_long_shell(log, "cmd", gen(), "running…"))
        await worker.wait()
        await pilot.pause()

        node = app.query(ToolNode).first()
        assert node.row.status == "complete"
        assert node.row.collapsed is True
        body = app.query(StreamingOutput).first()
        assert body.lines() == [f"out {i}" for i in range(5)]


@pytest.mark.asyncio
async def test_run_long_shell_esc_keeps_partial_output():
    """Core acceptance test: Esc mid-stream stops the run but the partial output
    stays in the panel (status 'stopped', lines visible, 'stopped' note dropped)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._pace = 0.0
        log = app.screen.query_one("#log", VerticalScroll)

        # Generator parks (forever) after 5 lines, guaranteeing the worker is
        # mid-stream when we interrupt — no reliance on wall-clock timing.
        blocked = asyncio.Event()

        async def gen():
            for i in range(5):
                yield f"line {i}"
            blocked.set()
            await asyncio.Event().wait()  # park until cancelled

        worker = app.run_worker(app._run_long_shell(log, "cmd", gen(), "running…"))
        app._turn_worker = worker

        for _ in range(400):
            await pilot.pause()
            if blocked.is_set():
                break
        assert blocked.is_set(), "stream never parked mid-run before interrupt"

        partial = len(app.query(StreamingOutput).first().lines())
        assert partial == 5
        await app.on_prompt_area_interrupt(None)
        for _ in range(20):
            await pilot.pause()

        node = app.query(ToolNode).first()
        assert node.row.status == "stopped"
        body = app.query(StreamingOutput).first()
        assert body.is_mounted
        assert len(body.lines()) >= partial  # partial output kept, not discarded
        assert len(body.query(OutputLine)) > 0
        assert any(n.message == "stopped" for n in app.query(SystemNote))
