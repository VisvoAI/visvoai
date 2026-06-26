"""Phase 2 — _render_tool_result maps each real tool to its Style-B body.

Deterministic (no network): drives the renderer directly with sample tool
outputs/args and asserts the right body widget + failure handling.
"""
import pytest

from textual.containers import VerticalScroll

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import CleanDiff, ToolOutput
from visvoai.cli.widgets.tool_row import ToolErrorBody


async def _render(app, name, args, output):
    log = app.query_one("#log", VerticalScroll)
    node = await app._tool_node(log, name, "x")
    await app._render_tool_result(node, name, args, output)
    return node


@pytest.mark.asyncio
async def test_edit_renders_diff():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        n = await _render(app, "edit_file",
                          {"path": "a.py", "old_string": "x=1", "new_string": "x=2\ny=3"},
                          "Replaced in /a.py")
        await pilot.pause()
        assert n.query(CleanDiff)
        assert n.row.rail == "+2 −1"


@pytest.mark.asyncio
async def test_edit_error_renders_failure():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        n = await _render(app, "edit_file", {"path": "a.py"}, "ERROR: old_string not found")
        await pilot.pause()
        assert n.query(ToolErrorBody)


@pytest.mark.asyncio
async def test_write_renders_content():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        n = await _render(app, "write_file",
                          {"path": "b.py", "content": "line1\nline2"}, "Wrote 11 chars to /b.py")
        await pilot.pause()
        assert n.query(ToolOutput)
        assert n.row.rail == "2 lines"


@pytest.mark.asyncio
async def test_shell_ok_vs_failure():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        ok = await _render(app, "run_shell", {"command": "ls"}, "a\nb\n[exit: 0]")
        await pilot.pause()
        assert ok.query(ToolOutput) and ok.row.rail == "exit 0"
        bad = await _render(app, "run_shell", {"command": "false"}, "boom\n[exit: 1]")
        await pilot.pause()
        assert bad.query(ToolErrorBody) and bad.row.rail == "exit 1"


@pytest.mark.asyncio
async def test_read_and_list_render_output():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        r = await _render(app, "read_file", {"path": "a.py"}, "1\tx=1\n2\ty=2")
        await pilot.pause()
        assert r.query(ToolOutput) and r.row.rail == "2 lines"
        ls = await _render(app, "list_files", {"path": "."}, "a/\nb.py\nc.py")
        await pilot.pause()
        assert ls.query(ToolOutput) and ls.row.rail == "3 items"


@pytest.mark.asyncio
async def test_read_error_renders_failure():
    """A read tool that reports an ERROR (missing file) renders as a failed node,
    not a fake success — and the agent gets the error back to recover from."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        n = await _render(app, "read_file", {"path": "nope.py"},
                          "ERROR: [Errno 2] No such file or directory: 'nope.py'")
        await pilot.pause()
        assert n.query(ToolErrorBody)
        assert n.row.rail == "failed"
