"""ToolRow + ToolGroup — Style B wired tool rendering (keystone)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import ToolGroup, ToolRow, verb_for


def test_verb_map():
    assert verb_for("read_file") == "read"
    assert verb_for("update_file") == "edit"
    assert verb_for("run_shell") == "run"
    assert verb_for("grep") == "search"
    assert verb_for("list_dir") == "list"
    assert verb_for("create") == "write"
    assert verb_for("unknown_tool") == "unknown_tool"   # graceful passthrough


def _row(row: ToolRow) -> str:
    return str(row.render())


@pytest.mark.asyncio
async def test_row_renders_verb_target_and_rail():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        row = ToolRow("read_file", "api/main.py", rail="124 lines · 8ms")
        await app.query_one("#log").mount(row)
        await pilot.pause()
        out = _row(row)
        assert "Read" in out and "api/main.py" in out   # display name, Title Case
        assert "124 lines · 8ms" in out


@pytest.mark.asyncio
async def test_status_glyph_in_rail():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        row = ToolRow("run_shell", "pytest -q")
        await app.query_one("#log").mount(row)
        await pilot.pause()
        row.set_status("complete")
        assert "✓" in _row(row)
        row.set_status("failed")
        assert "✗" in _row(row)
        row.set_status("stopped")
        assert "⊘" in _row(row)


@pytest.mark.asyncio
async def test_group_wires_connectors_last_gets_corner():
    """First row leads in with ╶─; the last row of a cluster gets └─; re-wires on add."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        g = ToolGroup()
        await app.query_one("#log").mount(g)
        r1 = await g.add(ToolRow("read_file", "a.py"))
        await pilot.pause()
        # a lone row reads as a single-line lead-in ╶─ (not the └─ corner)
        assert "╶─" in _row(r1)
        r2 = await g.add(ToolRow("read_file", "b.py"))
        await pilot.pause()
        # first row OPENS the wire downward (┌─); the last row gets the └─ corner
        assert "┌─" in _row(r1)
        assert "└─" in _row(r2)
        r3 = await g.add(ToolRow("read_file", "c.py"))
        await pilot.pause()
        # middle row now gets ├─
        assert "├─" in _row(r2)
        assert "└─" in _row(r3)


@pytest.mark.asyncio
async def test_running_starts_spinner_and_clears_on_done():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        row = ToolRow("run_shell", "pytest")
        await app.query_one("#log").mount(row)
        await pilot.pause()
        row.set_status("running")
        assert getattr(row, "_timer", None) is not None
        row.set_status("complete")
        assert getattr(row, "_timer", None) is None


# ── ToolNode: row + collapsible body + bg-panel-on-expand ────────────────────
from visvoai.cli.widgets import ToolNode, ToolErrorBody  # noqa: E402
from textual.widgets import Static  # noqa: E402


@pytest.mark.asyncio
async def test_node_set_body_collapsed_and_expand_panel():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        node = ToolNode("read_file", "api/main.py")
        await app.query_one("#log").mount(node)
        await pilot.pause()
        body = Static("file contents")
        await node.set_body(body, collapsed=True)
        await pilot.pause()
        assert body.display is False                  # collapsed → hidden
        assert not node.has_class("expanded")
        assert node.row.collapsible is True
        node.set_collapsed(False)
        assert body.display is True                   # expanded → shown
        assert node.has_class("expanded")             # → expanded breathing room
        assert body.has_class("tn-body")              # indented body


@pytest.mark.asyncio
async def test_node_click_toggles_body():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        node = ToolNode("read_file", "x.py")
        await app.query_one("#log").mount(node)
        await pilot.pause()
        await node.set_body(Static("body"), collapsed=True)
        node.on_tool_row_clicked(ToolRow.Clicked())
        assert node._body.display is True
        node.on_tool_row_clicked(ToolRow.Clicked())
        assert node._body.display is False


@pytest.mark.asyncio
async def test_node_set_failure_marks_row_and_lean_body():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        node = ToolNode("run_shell", "pytest -q")
        await app.query_one("#log").mount(node)
        await pilot.pause()
        body = await node.set_failure(
            ["test_x FAILED", "1 failed, 18 passed"], "expected 429, got 503")
        await pilot.pause()
        assert node.row.status == "failed"
        assert "✗" in str(node.row.render())
        assert isinstance(body, ToolErrorBody)
        out = str(body.render())
        assert "1 failed, 18 passed" in out and "expected 429, got 503" in out
        # no labels in the lean failure body
        assert "output" not in out and "┊" not in out


@pytest.mark.asyncio
async def test_node_mark_auto_applied_tags_rail():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        node = ToolNode("update_file", "utils.py")
        await app.query_one("#log").mount(node)
        await pilot.pause()
        node.mark_auto_applied()
        assert node.row.status == "complete"
        assert "auto-applied" in str(node.row.render())


@pytest.mark.asyncio
async def test_group_wires_nodes():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        g = ToolGroup()
        await app.query_one("#log").mount(g)
        n1 = await g.add(ToolNode("read_file", "a.py"))
        n2 = await g.add(ToolNode("read_file", "b.py"))
        await pilot.pause()
        assert "┌─" in str(n1.row.render())   # first row opens the wire downward
        assert "└─" in str(n2.row.render())   # last row corners
