"""Assistant markdown rendering + streaming.

The assistant reply is real markdown (headings, lists, inline/fenced code), not
plain text. These assert the block tree the `Markdown` widget builds and that
streaming a chunk at a time reconstructs the source exactly.
"""
from __future__ import annotations

import pytest
from textual.widgets._markdown import (
    MarkdownBulletList,
    MarkdownFence,
    MarkdownH3,
)

from visvoai.cli import VisvoApp
from visvoai.cli.demo import _stream_chunks
from visvoai.cli.mock import ASSISTANT_REPLY
from visvoai.cli.widgets import Assistant


def test_stream_chunks_reconstructs_source_with_newlines():
    text = "line one\n\n- a\n- b\n\n```toml\nx = 1\n```\n"
    assert "".join(_stream_chunks(text)) == text


async def _mount_streamed(app, pilot, text: str) -> Assistant:
    log = app.query_one("#log")
    a = Assistant()
    await log.mount(a)
    await pilot.pause()
    for chunk in _stream_chunks(text):
        await a.add(chunk)
    await pilot.pause()
    return a


@pytest.mark.asyncio
async def test_streamed_reply_builds_markdown_blocks():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        a = await _mount_streamed(app, pilot, ASSISTANT_REPLY)

        # streaming preserved the exact source…
        assert a.source == ASSISTANT_REPLY
        # …and produced the real block tree, not a single Text blob
        assert len(a.query(MarkdownH3)) == 1          # "### Changes"
        assert len(a.query(MarkdownBulletList)) == 1  # the 3-item list
        assert len(a.query(MarkdownFence)) == 1       # the ```toml block


@pytest.mark.asyncio
async def test_fenced_code_survives_partial_stream():
    """A half-streamed fence must not crash the incremental parser; once the
    closing ``` arrives it resolves to exactly one fence block."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        a = Assistant()
        await app.query_one("#log").mount(a)
        await pilot.pause()
        await a.add("```python\n")
        await a.add("x = 1\n")          # fence still open here
        await pilot.pause()
        await a.add("```\n")            # now closed
        await pilot.pause()
        assert len(a.query(MarkdownFence)) == 1


@pytest.mark.asyncio
async def test_markdown_survives_theme_switch():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        a = await _mount_streamed(app, pilot, ASSISTANT_REPLY)
        app.action_toggle_mode()       # fence re-highlights for the new mode
        await pilot.pause()
        assert len(a.query(MarkdownFence)) == 1
        assert a.source == ASSISTANT_REPLY
