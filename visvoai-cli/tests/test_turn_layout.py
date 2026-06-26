"""Minimal turn layout — user anchor (❯) per turn."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import SystemNote, ToolNode, UserMsg


@pytest.mark.asyncio
async def test_user_message_renders_anchor():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log")
        m = UserMsg("hello there")
        await log.mount(m)
        await pilot.pause()
        assert "❯ hello there" in str(m.render())


@pytest.mark.asyncio
async def test_block_grouping_gaps_between_categories_flush_within():
    """A gap (blk-gap) precedes a block only when its category changes; a run of
    consecutive tool calls stays flush as a cluster."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log")
        app._last_kind = None

        async def block(widget, kind):
            await app._mount_block(log, widget, kind)
            return widget

        first = await block(SystemNote("a"), "note")
        assert not first.has_class("blk-gap")               # first block: no gap
        ans = await block(SystemNote("b"), "answer")
        assert ans.has_class("blk-gap")                     # note → answer: gap
        t1 = await block(ToolNode("read_file", "x.py"), "tool")
        assert t1.has_class("blk-gap")                      # answer → tool: gap
        t2 = await block(ToolNode("read_file", "x.py"), "tool")
        t3 = await block(ToolNode("read_file", "x.py"), "tool")
        assert not t2.has_class("blk-gap")                  # tool → tool: flush cluster
        assert not t3.has_class("blk-gap")
        note = await block(SystemNote("c"), "note")
        assert note.has_class("blk-gap")                    # tool → note: gap
