"""AgentRunRegistry (structured steps, live trace, stop) + /runs + side panel."""
from __future__ import annotations

import json

import pytest

from visvoai.cli.agent_runs import RUN_CAP, AgentRunRegistry


# ── registry ─────────────────────────────────────────────────────────────────

def test_run_lifecycle_structured_steps():
    reg = AgentRunRegistry()
    reg.register("c1", "explore", "find the config loader")
    reg.step_start("c1", "r1", "run_shell", "rg -n config")
    assert reg.runs()[0].steps[0].status == "running"
    reg.step_end("c1", "r1", "src/config.py:12", ok=True)
    step = reg.runs()[0].steps[0]
    assert (step.tool, step.status, step.output) == ("run_shell", "complete",
                                                     "src/config.py:12")
    assert step.ended is not None
    reg.finish("c1", ok=True, summary="[agent: explore · 1 tool call · 4s]",
               final="Found it.")
    run = reg.runs()[0]
    assert run.status == "done" and run.final == "Found it."
    assert reg.running_count() == 0


def test_step_pairing_by_key_not_order():
    """Concurrent tool calls inside a run end out of order — pairing is by the
    event run_id, never append order."""
    reg = AgentRunRegistry()
    reg.register("c1", "general", "t")
    reg.step_start("c1", "a", "run_shell", "sleep 5")
    reg.step_start("c1", "b", "read_file", "x.py")
    reg.step_end("c1", "b", "contents", ok=True)      # b ends first
    steps = reg.runs()[0].steps
    assert steps[0].status == "running" and steps[1].status == "complete"


def test_failed_step_and_dying_run():
    reg = AgentRunRegistry()
    reg.register("c1", "explore", "t")
    reg.step_start("c1", "a", "run_shell", "boom")
    reg.step_end("c1", "a", "ERROR: nope", ok=False)
    reg.step_start("c1", "b", "run_shell", "hangs forever")
    reg.finish("c1", ok=False, summary="failed")       # run dies mid-step
    steps = reg.runs()[0].steps
    assert steps[0].status == "failed"
    assert steps[1].status == "failed"                 # no ✓ left pending


def test_live_trace_appends_per_step(tmp_path):
    """Durability: a hung run must leave its partial transcript on disk — meta
    at register, one line per completed step, summary only at finish."""
    reg = AgentRunRegistry()
    path = tmp_path / "explore_c1.jsonl"
    reg.register("c1", "explore", "scan", trace_path=path)
    reg.step_start("c1", "a", "run_shell", "rg -n foo")
    reg.step_end("c1", "a", "3 matches", ok=True)
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert [l["kind"] for l in lines] == ["meta", "step"]   # durable pre-finish
    assert lines[1]["tool"] == "run_shell" and lines[1]["ok"] is True
    reg.finish("c1", ok=True, summary="[agent: …]", final="done")
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert lines[-1]["kind"] == "summary" and lines[-1]["status"] == "done"


def test_stop_cancels_and_marks_user_stopped():
    reg = AgentRunRegistry()
    cancelled = []
    reg.register("c1", "explore", "t", cancel=lambda: cancelled.append(True))
    assert reg.stop("c1") is True
    assert cancelled == [True]
    assert reg.runs()[0].user_stopped
    reg.finish("c1", ok=False, summary="stopped by user")
    assert reg.runs()[0].status == "stopped"
    assert reg.stop("c1") is False                     # not running anymore


def test_runs_ordered_running_first_and_capped():
    reg = AgentRunRegistry()
    for i in range(RUN_CAP + 10):
        reg.register(f"c{i}", "explore", "t")
        reg.finish(f"c{i}", ok=True)
    reg.register("live", "general", "b")
    assert reg.runs()[0].dispatch_id == "live"
    assert len(reg.runs()) <= RUN_CAP + 1


# ── shared step rendering (RunStepsView = the conversation's ToolRows) ───────

@pytest.mark.asyncio
async def test_run_steps_render_as_tool_rows():
    from visvoai.cli import VisvoApp
    from visvoai.cli.widgets.run_steps import RunStepsView
    from visvoai.cli.widgets.tool_row import ToolRow

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        reg = app._agent_runs
        run = reg.register("c1", "explore", "scan")
        reg.step_start("c1", "a", "run_shell", "rg -n foo")
        reg.step_end("c1", "a", "3 matches", ok=True)
        reg.step_start("c1", "b", "read_file", "x.py")

        view = RunStepsView(run)
        await app.mount(view)
        view.sync()
        await pilot.pause()
        rows = list(view.query(ToolRow))
        assert len(rows) == 2
        assert rows[0].tool == "run_shell" and rows[0].status == "complete"
        assert rows[0].display_name == "Bash"      # SAME vocabulary as the chat
        assert rows[1].status == "running"
        # step completes → the SAME row transitions (no second line appended)
        reg.step_end("c1", "b", "contents", ok=True)
        view.sync()
        await pilot.pause()
        rows = list(view.query(ToolRow))
        assert len(rows) == 2 and rows[1].status == "complete"


@pytest.mark.asyncio
async def test_run_steps_tail_mode():
    from visvoai.cli import VisvoApp
    from visvoai.cli.widgets.run_steps import RunStepsView
    from visvoai.cli.widgets.tool_row import ToolRow

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        reg = app._agent_runs
        run = reg.register("c1", "explore", "scan")
        for i in range(8):
            reg.step_start("c1", f"k{i}", "run_shell", f"cmd {i}")
            reg.step_end("c1", f"k{i}", "ok", ok=True)
        view = RunStepsView(run, tail=3)
        await app.mount(view)
        view.sync()
        await pilot.pause()
        rows = list(view.query(ToolRow))
        assert len(rows) == 3
        assert "+5 earlier" in str(view.query_one(".rsv-more").render())


# ── /runs screen ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runs_screen_switch_and_stop():
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens import AgentRunsScreen
    from visvoai.cli.screens.runs_view import RunRow
    from visvoai.cli.widgets.run_steps import RunStepsView

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        reg = app._agent_runs
        cancelled = []
        reg.register("c1", "explore", "find flaky tests",
                      cancel=lambda: cancelled.append(True))
        reg.step_start("c1", "a", "run_shell", "pytest --collect-only")
        reg.register("c2", "performance-validator", "lighthouse audit")
        reg.finish("c2", ok=True, summary="[agent: …]", final="All good.")

        screen = AgentRunsScreen(reg)
        app.push_screen(screen)
        await pilot.pause()
        rows = list(screen.query(RunRow))
        assert len(rows) == 2
        log = screen.query_one(RunStepsView)
        assert log.run is not None and log.run.agent == "explore"  # running first
        await pilot.press("down")
        assert log.run.agent == "performance-validator"
        await pilot.press("up")
        await pilot.press("enter")                # stop the running one
        await pilot.pause()
        assert cancelled == [True]
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_runs_screen_empty_state():
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens import AgentRunsScreen

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = AgentRunsScreen(app._agent_runs)
        app.push_screen(screen)
        await pilot.pause()
        assert screen.query("#runs-empty")
        await pilot.press("escape")


# ── side panel ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_panel_appears_while_running_and_collapses_after():
    from visvoai.cli import VisvoApp
    from visvoai.cli.widgets.agent_panel import AgentPanel, _RunPane

    app = VisvoApp()
    async with app.run_test(size=(140, 40)) as pilot:   # wide enough for the split
        await pilot.pause()
        panel = app.query_one(AgentPanel)
        assert not panel.has_class("visible")           # idle → hidden

        app._agent_runs.register("c1", "explore", "scan the repo")
        app._agent_runs.step_start("c1", "a", "run_shell", "rg -n foo")
        app._sync_agent_panel()
        panel._tick()
        await pilot.pause()
        assert panel.has_class("visible")
        assert any(p.run.agent == "explore" for p in panel.query(_RunPane))

        app._agent_runs.finish("c1", ok=True)
        app._sync_agent_panel()
        await pilot.pause()
        assert not panel.has_class("visible")           # last one done → collapse


@pytest.mark.asyncio
async def test_agent_panel_stays_hidden_on_narrow_terminal():
    from visvoai.cli import VisvoApp
    from visvoai.cli.widgets.agent_panel import AgentPanel

    app = VisvoApp()
    async with app.run_test(size=(80, 30)) as pilot:    # classic 80-col terminal
        await pilot.pause()
        app._agent_runs.register("c1", "explore", "scan")
        app._sync_agent_panel()
        await pilot.pause()
        assert not app.query_one(AgentPanel).has_class("visible")


@pytest.mark.asyncio
async def test_footer_agents_chip_and_click_opens_runs():
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens import AgentRunsScreen
    from visvoai.cli.widgets.status import StatusBar, _AgentsChip

    app = VisvoApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        app._agent_runs.register("c1", "explore", "scan")
        app._agent_runs.register("c2", "general", "fix")
        app._sync_agent_panel()
        await pilot.pause()
        chip = app.query_one("#sb-agents", _AgentsChip)
        assert "2 agents" in str(chip.render())
        app.post_message(StatusBar.AgentsChipClicked())
        await pilot.pause()
        assert isinstance(app.screen, AgentRunsScreen)
        await pilot.press("escape")
        await pilot.pause()
        app._agent_runs.finish("c1", ok=True)
        app._agent_runs.finish("c2", ok=True)
        app._sync_agent_panel()
        await pilot.pause()
        assert str(app.query_one("#sb-agents", _AgentsChip).render()).strip() == ""


# ── run_agent row rendering ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_agent_result_row_rail():
    """_render_tool_result('run_agent'): trailer → rail, report → collapsed
    body; ERROR output → failed row. (Registry lifecycle is the tool's job.)"""
    from textual.containers import VerticalScroll

    from visvoai.cli import VisvoApp

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log", VerticalScroll)

        node = await app._tool_node(log, "run_agent", "explore — scan")
        out = ("Found it in src/x.py:12\n"
               "[agent: explore · 3 tool calls · 8.1k tokens · $0.0021 · 12s]")
        await app._render_tool_result(node, "run_agent", {"agent": "explore"}, out)
        assert node.row.status == "complete"
        assert "3 tool calls" in node.row.rail and "12s" in node.row.rail

        node2 = await app._tool_node(log, "run_agent", "general — fix")
        await app._render_tool_result(node2, "run_agent", {"agent": "general"},
                                      "ERROR: agent 'general' failed: boom")
        assert node2.row.status == "failed"
