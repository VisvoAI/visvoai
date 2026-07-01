"""The /rewind picker is turn-oriented: one entry per USER QUESTION (newest first),
each mapping to 'the moment just before you asked it', with an activity summary. This
is the fix for 'I can only rewind to tools, not to my question'."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo
from visvoai.cli.rewind import _turn_activity

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _tc(name, id, **args):
    return {"name": name, "args": args, "id": id, "type": "tool_call"}


def test_turn_activity_summarizes_tools():
    msgs = [AIMessage(content="", tool_calls=[_tc("read_file", "1", path="src/api.py"),
                                              _tc("run_shell", "2", command="pytest")]),
            ToolMessage(content="ok", tool_call_id="1"),
            ToolMessage(content="ok", tool_call_id="2")]
    s = _turn_activity(msgs)
    assert "read api.py" in s and "ran pytest" in s


def test_turn_activity_plain_reply():
    assert _turn_activity([AIMessage(content="here is the answer")]).startswith("replied:")


@pytest.mark.asyncio
async def test_rewind_entries_are_one_per_question_incl_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        app._maybe_baseline()
        for i in range(1, 4):                     # 3 questions
            app._history += [HumanMessage(content=f"question {i}"), AIMessage(content=f"a{i}")]
            (proj / "a.txt").write_text(f"v{i+1}\n")
            app._record_checkpoint(len(app._history), "turn", f"question {i}")

        entries = app._turn_rewind_entries(app._timeline())
        # one entry per question, newest first, INCLUDING the latest (undo last turn)
        assert [e["question"] for e in entries] == ["question 3", "question 2", "question 1"]
        assert [e["n"] for e in entries] == [3, 2, 1]


@pytest.mark.asyncio
async def test_rewind_screen_renders_turn_rows_and_selects(tmp_path):
    from visvoai.cli.screens.rewind_view import RewindScreen, TurnRow
    entries = [
        {"id": "b2", "n": 2, "question": "add tests", "activity": "wrote test_x.py",
         "files": 1, "when": "2m ago"},
        {"id": "b1", "n": 1, "question": "add a rate limiter", "activity": "edited api.py",
         "files": 2, "when": "5m ago"},
    ]
    chosen = {}
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(RewindScreen(entries), lambda cid: chosen.setdefault("id", cid))
        for _ in range(10):
            await pilot.pause()
            if isinstance(app.screen, RewindScreen):
                break
        rows = list(app.screen.query(TurnRow))
        assert len(rows) == 2                                # two-line question rows
        assert rows[0].entry["question"] == "add tests"      # newest first, as passed
        await pilot.press("down")                            # highlight 2nd
        await pilot.press("enter")
        await pilot.pause()
        assert chosen["id"] == "b1"                           # selected question's checkpoint


@pytest.mark.asyncio
async def test_rewind_to_a_question_restores_before_it(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        app._maybe_baseline()
        # turn 1 → v2
        app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
        (proj / "a.txt").write_text("v2\n")
        app._record_checkpoint(len(app._history), "turn", "q1")
        # turn 2 → v3
        app._history += [HumanMessage(content="q2"), AIMessage(content="a2")]
        (proj / "a.txt").write_text("v3\n")
        app._record_checkpoint(len(app._history), "turn", "q2")
        store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)

        entries = app._turn_rewind_entries(app._timeline())
        q2 = next(e for e in entries if e["question"] == "q2")
        row = next(r for r in app._timeline() if r["checkpoint_id"] == q2["id"])

        await app._apply_rewind(row)              # "rewind to before q2"
        await pilot.pause()

        assert (proj / "a.txt").read_text() == "v2\n"   # files as they were before q2
        assert [m.content for m in app._history] == ["q1", "a1"]   # q2 onward dropped
