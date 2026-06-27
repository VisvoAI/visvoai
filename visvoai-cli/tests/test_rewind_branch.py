"""Plan E — branching & switching: fork keeps both timelines; switch restores each
branch's thread + code. Runs under a live app (replay path executes)."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


async def _two_turn_conv(app, proj):
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(2, "turn", "q1")
    store.append_receipt(app._project_id, app._conv_id, {"seconds": 1, "model": "m", "cost": 0.1})
    app._history += [HumanMessage(content="q2"), AIMessage(content="a2")]
    (proj / "a.txt").write_text("v3\n")
    app._record_checkpoint(4, "turn", "q2")
    store.append_receipt(app._project_id, app._conv_id, {"seconds": 1, "model": "m", "cost": 0.2})
    store.save_conversation(app._project_id, app._conv_id, app._history)
    app._persisted_count = 4


@pytest.mark.asyncio
async def test_branch_from_keeps_both_timelines(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turn_conv(app, proj)
        records = store.read_checkpoints(app._project_id, app._conv_id)
        turn1 = next(c for c in records if c["label"] == "q1")

        await app._branch_from(turn1, "alt")
        await pilot.pause()

        # active is the new branch, forked at turn1 (code v2, thread truncated)
        assert app._cp_branch == "alt"
        assert (proj / "a.txt").read_text() == "v2\n"
        assert len(app._history) == 2
        # main's full thread was preserved on disk
        assert len(store.load_branch_thread(app._project_id, app._conv_id, "main")) == 4
        # both branch tips known
        assert set(app._cp_branch_tips) == {"main", "alt"}


@pytest.mark.asyncio
async def test_switch_restores_each_branch_thread_and_code(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turn_conv(app, proj)
        records = store.read_checkpoints(app._project_id, app._conv_id)
        turn1 = next(c for c in records if c["label"] == "q1")
        await app._branch_from(turn1, "alt")
        await pilot.pause()
        # do work on alt → v2-alt
        app._history += [HumanMessage(content="q3"), AIMessage(content="a3")]
        (proj / "a.txt").write_text("v2-alt\n")
        app._record_checkpoint(4, "turn", "q3")
        store.save_conversation(app._project_id, app._conv_id, app._history)

        # switch back to main → its thread (4 msgs) + code (v3) restored
        await app._switch_branch("main")
        await pilot.pause()
        assert app._cp_branch == "main"
        assert (proj / "a.txt").read_text() == "v3\n"
        assert len(app._history) == 4

        # switch back to alt → its thread (4 msgs) + code (v2-alt)
        await app._switch_branch("alt")
        await pilot.pause()
        assert (proj / "a.txt").read_text() == "v2-alt\n"
        assert len(app._history) == 4
        assert app._history[-1].content == "a3"


def test_branch_entries_marks_current(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._record_checkpoint(1, "turn", "q1")
    records = store.read_checkpoints(app._project_id, app._conv_id)
    entries = app._branch_entries(records)
    assert entries[0]["name"] == "main" and entries[0]["current"] is True
