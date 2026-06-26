"""Phase 3 — permission gate on mutating tools + the _approve HITL.

Gate mechanism (gated_tools): approve→mutate, deny→no mutation, reads ungated.
_approve UI: --yolo bypass, 'allow all this session', Yes/No via the Selection.
"""
import os
import tempfile

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.gated_tools import build_gated_tools
from visvoai.cli.widgets import Selection


# ── gate mechanism (no UI) ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gate_allows_and_blocks_mutations():
    d = tempfile.mkdtemp()
    f = os.path.join(d, "x.txt")
    calls = []

    async def yes(name, args):
        calls.append(name)
        return True

    async def no(name, args):
        return False

    allow = {t.name: t for t in build_gated_tools(d, yes)}
    deny = {t.name: t for t in build_gated_tools(d, no)}

    assert "Wrote" in await allow["write_file"].ainvoke({"path": f, "content": "hello"})
    assert os.path.exists(f)

    blocked = os.path.join(d, "y.txt")
    assert "declined" in await deny["write_file"].ainvoke({"path": blocked, "content": "no"})
    assert not os.path.exists(blocked)  # denial means NO mutation

    assert "Replaced" in await allow["edit_file"].ainvoke(
        {"path": f, "old_string": "hello", "new_string": "world"})
    assert open(f).read() == "world"
    assert "exit: 0" in await allow["run_shell"].ainvoke({"command": "echo hi"})
    # reads are never gated → approve never called for them
    await allow["read_file"].ainvoke({"path": f})
    assert calls == ["write_file", "edit_file", "run_shell"]


# ── _approve HITL ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_accept_all_mode_bypasses_prompt():
    from visvoai.cli.hitl_modes import HITLMode

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._hitl_mode = HITLMode.ACCEPT_ALL
        assert await app._approve("edit_file", {"path": "a.py"}) is True
        assert await app._approve("run_shell", {"command": "ls"}) is True
        assert not app.query(Selection)  # no prompt shown


@pytest.mark.asyncio
async def test_auto_edit_mode_gates_shell_only():
    from visvoai.cli.hitl_modes import HITLMode

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._hitl_mode = HITLMode.AUTO_EDIT
        # file edits auto-approved, no prompt
        assert await app._approve("edit_file", {"path": "a.py"}) is True
        assert await app._approve("write_file", {"path": "a.py"}) is True
        assert not app.query(Selection)


async def _drive_approve(app, pilot, tool, args, choice):
    w = app.run_worker(app._approve(tool, args))
    for _ in range(40):
        await pilot.pause()
        if app.query(Selection):
            break
    app.query(Selection).first()._resolve((choice, ""))
    await w.wait()
    return w.result


@pytest.mark.asyncio
async def test_approve_yes_no():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert await _drive_approve(app, pilot, "edit_file", {"path": "a"}, 0) is True
        assert await _drive_approve(app, pilot, "edit_file", {"path": "a"}, 2) is False


@pytest.mark.asyncio
async def test_allow_all_sticks_per_tool():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # choice 1 = "allow all this session"
        assert await _drive_approve(app, pilot, "run_shell", {"command": "ls"}, 1) is True
        assert "run_shell" in app._approved_all
        # subsequent run_shell calls bypass the prompt
        assert await app._approve("run_shell", {"command": "pwd"}) is True
        assert not app.query(Selection)
