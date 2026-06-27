"""Plan C — applying a rewind: files restored to the checkpoint, the branch's thread +
receipts + timeline truncated to its message index, and the tip moved. Runs under a
live app so the UI replay path executes."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("v1\n")
    return proj


def _row(app, label):
    rows = store.read_timeline(app._project_id, app._conv_id, "main")
    return next(r for r in rows if r["label"] == label)


@pytest.mark.asyncio
async def test_rewind_restores_files_and_truncates_thread(tmp_path, monkeypatch):
    proj = _setup(tmp_path, monkeypatch)
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()

        app._maybe_baseline()                                   # baseline @ v1
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

        turn1 = _row(app, "q1")
        await app._apply_rewind(turn1)
        await pilot.pause()

        assert (proj / "a.txt").read_text() == "v2\n"
        assert len(app._history) == 2
        assert store.load_conversation(app._project_id, app._conv_id) == app._history
        assert len(store.read_receipts(app._project_id, app._conv_id)) == 1
        assert app._cp_tip_id == turn1["checkpoint_id"]
        # timeline truncated to the target (baseline + turn1)
        assert len(store.read_timeline(app._project_id, app._conv_id, "main")) == 2


@pytest.mark.asyncio
async def test_rewind_to_baseline_clears_thread_and_restores_pristine(tmp_path, monkeypatch):
    proj = _setup(tmp_path, monkeypatch)
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        app._maybe_baseline()
        app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
        (proj / "a.txt").write_text("v2\n")
        (proj / "new.txt").write_text("created\n")
        app._record_checkpoint(2, "turn", "q1")
        store.save_conversation(app._project_id, app._conv_id, app._history)

        baseline = _row(app, "start")
        await app._apply_rewind(baseline)
        await pilot.pause()

        assert (proj / "a.txt").read_text() == "v1\n"
        assert not (proj / "new.txt").exists()
        assert app._history == []


def test_completed_turns_counts_only_closed_turns():
    app = VisvoApp()
    from langchain_core.messages import ToolMessage
    assert app._completed_turns([]) == 0
    assert app._completed_turns([HumanMessage(content="q"), AIMessage(content="a")]) == 1
    assert app._completed_turns([HumanMessage(content="q"), AIMessage(content="a"),
                                 HumanMessage(content="q2")]) == 1
    pend = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1", "type": "tool_call"}])
    assert app._completed_turns([HumanMessage(content="q"), pend]) == 0
