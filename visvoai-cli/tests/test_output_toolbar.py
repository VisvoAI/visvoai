"""Output tier-2 tests — OutputToolbar (search / save / jump-to-failure)."""
from __future__ import annotations

import os

import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import OutputToolbar, ToolOutput
from visvoai.cli.widgets.output import OutputLine
from visvoai.cli.widgets.output_toolbar import SearchInput, SearchRow
from visvoai.cli.widgets.streaming_output import StreamingOutput


async def _mount(app, widget):
    log = app.screen.query_one("#log", VerticalScroll)
    await log.mount(widget)


@pytest.mark.asyncio
async def test_toolbar_hidden_when_not_truncated():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput(["a", "b", "c"], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        assert len(out.query(OutputToolbar)) == 0


@pytest.mark.asyncio
async def test_toolbar_visible_when_truncated():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(20)], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        assert len(out.query(OutputToolbar)) == 1


@pytest.mark.asyncio
async def test_toolbar_hidden_when_tier2_disabled():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(20)], max_lines=12, tier2=False)
        await _mount(app, out)
        await pilot.pause()
        assert len(out.query(OutputToolbar)) == 0


@pytest.mark.asyncio
async def test_search_opens_input():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(20)], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._open_search()
        await pilot.pause()
        assert len(out.query(SearchInput)) == 1


@pytest.mark.asyncio
async def test_search_highlights_matches():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        lines = [f"line {i}" for i in range(20)]
        lines[3] = "this one FAILED hard"
        lines[15] = "another FAILED here"
        out = ToolOutput(lines, max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._open_search()
        si = out.query_one(SearchInput)
        si.value = "FAILED"
        si.post_message(SearchInput.Query("FAILED"))
        await pilot.pause()
        assert out._match_indices == [3, 15]
        # the matched line widget renders the substring (highlight applied)
        rendered = out._line_widgets[3].render()
        assert "FAILED" in rendered.plain


@pytest.mark.asyncio
async def test_search_enter_advances_to_next_match():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        lines = [f"line {i}" for i in range(30)]
        for idx in (2, 10, 20):
            lines[idx] = f"hit MATCH at {idx}"
        out = ToolOutput(lines, max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._open_search()
        si = out.query_one(SearchInput)
        si.post_message(SearchInput.Query("MATCH"))
        await pilot.pause()
        assert out._current_match == 0
        si.post_message(SearchInput.Next())
        si.post_message(SearchInput.Next())
        await pilot.pause()
        assert out._current_match == 2


@pytest.mark.asyncio
async def test_search_esc_closes():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(20)], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._open_search()
        si = out.query_one(SearchInput)
        si.post_message(SearchInput.Query("line"))
        await pilot.pause()
        si.post_message(SearchInput.Closed())
        await pilot.pause()
        assert len(out.query(SearchRow)) == 0
        assert out._match_indices == []


@pytest.mark.asyncio
async def test_search_no_matches_shows_error_color():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(20)], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._open_search()
        si = out.query_one(SearchInput)
        si.value = "xyz123"
        si.post_message(SearchInput.Query("xyz123"))
        await pilot.pause()
        assert out._match_indices == []
        assert si.has_class("no-match")


@pytest.mark.asyncio
async def test_save_writes_buffer_to_file():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        lines = [f"line {i}" for i in range(20)]
        out = ToolOutput(lines, max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        path = out._save_buffer()
        try:
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == "\n".join(lines)
        finally:
            os.remove(path)


@pytest.mark.asyncio
async def test_jump_to_failure_scrolls_to_first_error():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        lines = [f"line {i}" for i in range(60)]
        lines[47] = "test_thing FAILED here"
        out = ToolOutput(lines, max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        await out._jump_failure()
        await pilot.pause()
        # jump expands the full buffer so line 47 is now mounted/visible
        assert any("FAILED" in w.render().plain for w in out._line_widgets)
        assert len(out._line_widgets) == 60


@pytest.mark.asyncio
async def test_jump_to_failure_noop_when_no_failures():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = ToolOutput([f"line {i}" for i in range(60)], max_lines=12, tier2=True)
        await _mount(app, out)
        await pilot.pause()
        before = len(out._line_widgets)
        await out._jump_failure()
        await pilot.pause()
        # no error pattern → no expand, no change
        assert len(out._line_widgets) == before


@pytest.mark.asyncio
async def test_toolbar_hidden_while_streaming():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = StreamingOutput(max_lines=12, tier2=True)
        await _mount(app, out)
        for i in range(20):
            out.add_line(f"line {i}")
        await pilot.pause()
        assert len(out.query(OutputToolbar)) == 0


@pytest.mark.asyncio
async def test_toolbar_visible_after_finalize():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        out = StreamingOutput(max_lines=12, tier2=True)
        await _mount(app, out)
        for i in range(20):
            out.add_line(f"line {i}")
        out.finalize()
        await pilot.pause()
        assert len(out.query(OutputToolbar)) == 1
