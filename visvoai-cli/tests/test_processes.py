"""ProcessRegistry + background tools: spawn, output, group kill, cleanup."""
from __future__ import annotations

import asyncio
import subprocess
import time

import pytest

from visvoai.cli.processes import ProcessRegistry, describe_cmd


def _wait(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def registry():
    r = ProcessRegistry()
    yield r
    r.stop_all()


def test_spawn_and_incremental_output(registry):
    info = registry.spawn("echo one; sleep 0.3; echo two; sleep 30")
    assert info.status == "running" and info.id == "p1"
    proc = registry.get("p1")
    assert _wait(lambda: proc.total_lines >= 2)
    first = proc.read_new()
    assert "one" in first and "two" in first
    assert proc.read_new() == ""              # cursor advanced — nothing new
    proc.stop("agent")
    assert proc.status() == "stopped"


def test_group_kill_reaches_children(registry):
    # Parent spawns a child; killing the group must take the child too.
    registry.spawn("sh -c 'sleep 60 & echo child_pid $!; wait'")
    proc = registry.get("p1")
    assert _wait(lambda: proc.total_lines >= 1)
    child_pid = int(proc.read_new().split()[-1])
    proc.stop("user")
    assert proc.status() == "stopped"
    assert proc.stopped_by == "user"

    def child_gone():
        # signal 0 probes existence
        try:
            import os
            os.kill(child_pid, 0)
            return False
        except ProcessLookupError:
            return True
    assert _wait(child_gone), "child survived the group kill"


def test_natural_exit_and_dismiss(registry):
    registry.spawn("echo done")
    proc = registry.get("p1")
    assert _wait(lambda: proc.status() == "exited")
    assert proc.info().returncode == 0
    assert registry.dismiss("p1") is True
    assert registry.get("p1") is None
    assert registry.dismiss("p1") is False


def test_dismiss_refuses_running(registry):
    registry.spawn("sleep 30")
    assert registry.dismiss("p1") is False    # running — must stop first
    assert registry.get("p1") is not None


def test_stop_all_and_counts(registry):
    registry.spawn("sleep 30")
    registry.spawn("sleep 30")
    assert registry.running_count() == 2
    registry.stop_all()
    assert _wait(lambda: registry.running_count() == 0)


def test_ring_buffer_caps_and_reports_drop(registry):
    registry.spawn("i=0; while [ $i -lt 3000 ]; do echo line$i; i=$((i+1)); done")
    proc = registry.get("p1")
    assert _wait(lambda: proc.status() == "exited")
    out = proc.read_new()
    assert "earlier lines dropped" in out
    assert "line2999" in out


def test_describe_cmd():
    assert describe_cmd("yarn   dev") == "yarn dev"
    assert describe_cmd("x" * 100, width=10).endswith("…")


# ── tools ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_background_tools_lifecycle(registry):
    from visvoai.cli.tools.background import build_background_tools

    tools = {t.name: t for t in build_background_tools(registry)}
    out = await tools["start_process"].coroutine(command="echo ready; sleep 30")
    assert "started p1" in out

    out = await tools["check_process"].coroutine(process_id="p1", wait_seconds=1)
    assert "ready" in out and "status: running" in out

    out = await tools["stop_process"].coroutine(process_id="p1")
    assert "stopped p1" in out

    out = await tools["check_process"].coroutine(process_id="p1")
    assert "stopped by the agent" in out

    out = await tools["check_process"].coroutine(process_id="p99")
    assert "unknown process" in out


@pytest.mark.asyncio
async def test_background_tools_gating(registry):
    from visvoai.cli.tools.background import build_background_tools, _DENIED

    decisions = []

    async def approve(name, args):
        decisions.append(name)
        return name != "start_process"    # deny starts, allow stops

    tools = {t.name: t for t in build_background_tools(registry, approve=approve)}
    out = await tools["start_process"].coroutine(command="sleep 30")
    assert out == _DENIED
    assert registry.list() == []          # nothing spawned on deny
    # check is never gated
    await tools["check_process"].coroutine(process_id="p1")
    assert decisions == ["start_process"]


@pytest.mark.asyncio
async def test_check_process_returns_early_on_exit(registry):
    from visvoai.cli.tools.background import build_background_tools

    tools = {t.name: t for t in build_background_tools(registry)}
    await tools["start_process"].coroutine(command="echo bye")
    t0 = time.time()
    out = await tools["check_process"].coroutine(process_id="p1", wait_seconds=30)
    assert time.time() - t0 < 5           # returned on exit, not after 30s
    assert "exited (code 0)" in out


# ── ProcessScreen (pilot) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_screen_stop_and_dismiss(registry):
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens.process_view import ProcessScreen, ProcRow

    registry.spawn("echo hello-world; sleep 30")     # p1 running
    registry.spawn("echo done-already")              # p2 exits
    proc2 = registry.get("p2")
    assert _wait(lambda: proc2.status() == "exited")

    app = VisvoApp()
    async with app.run_test() as pilot:
        screen = ProcessScreen(registry)
        app.push_screen(screen)
        await pilot.pause()

        rows = list(screen.query(ProcRow))
        assert [r.proc.id for r in rows] == ["p1", "p2"]   # running first

        # enter on p1 → stop (user)
        await pilot.press("enter")
        await pilot.pause()
        assert _wait(lambda: registry.get("p1").status() == "stopped")
        assert registry.get("p1").stopped_by == "user"

        # both now stopped/exited; enter dismisses the selected one
        await pilot.press("enter")
        await pilot.pause()
        assert len(registry.list()) == 1

        await pilot.press("escape")
        await pilot.pause()


@pytest.mark.asyncio
async def test_process_screen_empty_state(registry):
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens.process_view import ProcessScreen

    app = VisvoApp()
    async with app.run_test() as pilot:
        screen = ProcessScreen(registry)
        app.push_screen(screen)
        await pilot.pause()
        assert "Nothing running" in str(screen.query_one("#ps-empty").render())
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_app_unmount_kills_processes():
    from visvoai.cli import VisvoApp

    app = VisvoApp()
    async with app.run_test() as pilot:
        app._processes.spawn("sleep 60")
        assert app._processes.running_count() == 1
    # run_test teardown unmounts the app → on_unmount stop_all
    assert _wait(lambda: app._processes.running_count() == 0)


def test_footer_chip_hidden_at_zero():
    from visvoai.cli.widgets.status import StatusBar
    bar = StatusBar()
    bar.set_processes(0)
    assert bar._processes == 0
    bar.set_processes(2)
    assert bar._processes == 2


@pytest.mark.asyncio
async def test_status_updates_are_noops_after_teardown():
    """A cancelled turn's finally block calls _set_status/_set_context after the
    widgets are gone — must be a no-op, not NoMatches (the wild crash)."""
    from visvoai.cli import VisvoApp

    app = VisvoApp()
    async with app.run_test():
        pass
    # App torn down — these were raising NoMatches from the worker's finally.
    app._set_status(None)
    app._set_context(50, 1000)
    app._update_cost_status()
