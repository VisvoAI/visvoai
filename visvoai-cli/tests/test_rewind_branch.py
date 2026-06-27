"""Plan E — branching & switching: fork keeps both timelines (and is isolated from
later changes to the parent); switch restores each branch's thread + code."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _row(app, label):
    rows = store.read_timeline(app._project_id, app._conv_id, app._cp_branch)
    return next(r for r in rows if r["label"] == label)


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
        turn1 = _row(app, "q1")
        await app._branch_from(turn1, "alt")
        await pilot.pause()

        assert app._cp_branch == "alt"
        assert (proj / "a.txt").read_text() == "v2\n"
        assert len(app._history) == 2
        # main's full thread preserved
        assert len(store.load_branch_thread(app._project_id, app._conv_id, "main")) == 4
        assert set(store.list_branches(app._project_id, app._conv_id)) == {"main", "alt"}
        # provenance recorded, never used for reconstruction
        assert store.read_branch_meta(app._project_id, app._conv_id, "alt")["forked_from"]["branch"] == "main"


@pytest.mark.asyncio
async def test_fork_is_isolated_from_later_parent_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turn_conv(app, proj)
        turn1 = _row(app, "q1")
        await app._branch_from(turn1, "alt")
        await pilot.pause()
        alt_thread_before = store.load_branch_thread(app._project_id, app._conv_id, "alt")

        # go back to main and rewind IT — must not touch alt
        await app._switch_branch("main")
        await pilot.pause()
        await app._apply_rewind(_row(app, "q1"))   # main now has only q1
        await pilot.pause()

        assert store.load_branch_thread(app._project_id, app._conv_id, "alt") == alt_thread_before


@pytest.mark.asyncio
async def test_switch_restores_each_branch_thread_and_code(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turn_conv(app, proj)
        await app._branch_from(_row(app, "q1"), "alt")
        await pilot.pause()
        # diverge alt → v2-alt
        app._history += [HumanMessage(content="q3"), AIMessage(content="a3")]
        (proj / "a.txt").write_text("v2-alt\n")
        app._record_checkpoint(4, "turn", "q3")
        store.save_conversation(app._project_id, app._conv_id, app._history)

        await app._switch_branch("main")
        await pilot.pause()
        assert app._cp_branch == "main"
        assert (proj / "a.txt").read_text() == "v3\n"
        assert len(app._history) == 4

        await app._switch_branch("alt")
        await pilot.pause()
        assert (proj / "a.txt").read_text() == "v2-alt\n"
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
    entries = app._branch_entries()
    assert entries[0]["name"] == "main" and entries[0]["current"] is True
