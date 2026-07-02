"""ReadChainGroup tests — wired multi-hop read chain + dead-end backtracks."""
from __future__ import annotations

import pytest

from textual.containers import VerticalScroll
from textual.widgets import Static

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import ReadChainGroup
from visvoai.cli.widgets.tool_row import ToolNode


async def _group(app, label="investigation"):
    log = app.screen.query_one("#log", VerticalScroll)
    group = ReadChainGroup(label)
    await log.mount(group)
    return group


def _node(i: int) -> ToolNode:
    return ToolNode("read_file", f"file_{i}.py", rail="40 lines")


@pytest.mark.asyncio
async def test_read_chain_group_mounts_with_header():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app, "trace")
        await pilot.pause()
        header = group.query_one(".chain-header", Static).render()
        assert "trace" in header.plain
        assert "0 reads" in header.plain


@pytest.mark.asyncio
async def test_read_chain_add_node_and_count():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app)
        for i in range(3):
            await group.add_node(_node(i))
        await pilot.pause()
        assert len(group.query(ToolNode)) == 3
        assert "3 reads" in group.query_one(".chain-header", Static).render().plain


@pytest.mark.asyncio
async def test_read_chain_wires_connectors():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app)
        for i in range(3):
            await group.add_node(_node(i))
        await pilot.pause()
        rows = [n.row for n in group.nodes()]
        for row in rows:                        # uniform single-line tick — no spine
            assert "╶─" in str(row.render())


@pytest.mark.asyncio
async def test_read_chain_mark_backtrack_marks_dead_end():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app)
        for i in range(5):
            await group.add_node(_node(i))
        await pilot.pause()
        group.mark_backtrack(2)
        await pilot.pause()
        dead = group.nodes()[2]
        assert dead.row.status == "stopped"
        out = str(dead.row.render())
        assert "dead end" in out
        assert "⊘" in out
        # the other reads are unaffected
        assert group.nodes()[0].row.status != "stopped"


@pytest.mark.asyncio
async def test_read_chain_header_single_cell_glyph():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app, "investigation")
        await pilot.pause()
        header = group.query_one(".chain-header", Static).render().plain
        assert header.startswith("◎ ")     # single-cell glyph, not an emoji
        assert "🔍" not in header


@pytest.mark.asyncio
async def test_read_chain_nodes_indent():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app)
        await group.add_node(_node(0))
        await pilot.pause()
        node = group.query_one(ToolNode)
        # +2 indent from the chain's col 3 → child content at col 5 (SUBITEM)
        assert node.styles.padding.left == 2


@pytest.mark.asyncio
async def test_read_chain_nodes_returns_ordered_list():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        group = await _group(app)
        nodes = [_node(i) for i in range(5)]
        for n in nodes:
            await group.add_node(n)
        await pilot.pause()
        assert group.nodes() == nodes
