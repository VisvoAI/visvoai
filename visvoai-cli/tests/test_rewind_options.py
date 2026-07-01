"""The granular rewind options: revert conversation only (#2), revert code only (#3),
and summarize-up-to (#5 via _compact_to). #1 (code + conversation) is covered by
test_rewind_apply."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from visvoai.cli import VisvoApp, agent, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


async def _async(v):
    return v


async def _two_turns(app, proj):
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(len(app._history), "turn", "q1")
    app._history += [HumanMessage(content="q2"), AIMessage(content="a2")]
    (proj / "a.txt").write_text("v3\n")
    app._record_checkpoint(len(app._history), "turn", "q2")
    store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)
    app._persisted_count = len(app._history)


def _row(app, label):
    return next(r for r in app._timeline() if r["label"] == label)


def _boundary_row(app, question):
    """The timeline row the /rewind flow targets for `question` — i.e. the checkpoint at
    the start of that question (via the turn-view entry's id), same as _rewind_flow."""
    entry = next(e for e in app._turn_rewind_entries(app._timeline()) if e["question"] == question)
    return next(r for r in app._timeline() if r["checkpoint_id"] == entry["id"])


@pytest.mark.asyncio
async def test_revert_conversation_only_keeps_files(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turns(app, proj)
        await app._revert_conversation_only(_row(app, "q1"))   # rewind chat to before q2
        await pilot.pause()
        assert [m.content for m in app._history] == ["q1", "a1"]   # chat truncated
        assert (proj / "a.txt").read_text() == "v3\n"              # FILES KEPT (current)
        assert store.load_branch_thread(app._project_id, app._conv_id, "main") == app._history


@pytest.mark.asyncio
async def test_revert_code_only_keeps_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turns(app, proj)
        before = list(app._history)
        await app._revert_code_only(_row(app, "q1"))              # files back to after-q1
        await pilot.pause()
        assert app._history == before                              # CHAT KEPT (full)
        assert (proj / "a.txt").read_text() == "v2\n"             # files reverted
        # a fresh 'edit' checkpoint captured the reverted tree at the thread end
        rows = store.read_timeline(app._project_id, app._conv_id, "main")
        assert rows[-1]["kind"] == "edit"
        assert rows[-1]["message_index"] == len(app._history)


@pytest.mark.asyncio
async def test_summarize_up_to_here_folds_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    monkeypatch.setattr(agent, "summarize_history", lambda *a, **k: _async("SUMMARY"))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turns(app, proj)
        q2 = _boundary_row(app, "q2")                              # cut at q2's start
        await app._compact_to(q2["message_index"])
        await pilot.pause()
        # everything before q2 folded → [summary] + [q2, a2]
        assert isinstance(app._history[0], SystemMessage)
        assert [m.content for m in app._history[1:]] == ["q2", "a2"]


@pytest.mark.asyncio
async def test_summarize_up_to_here_noop_at_first_question(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    called = {"n": 0}
    async def _spy(*a, **k):
        called["n"] += 1; return "x"
    monkeypatch.setattr(agent, "summarize_history", _spy)
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_turns(app, proj)
        q1 = _boundary_row(app, "q1")
        # q1 is the first question → its boundary is the baseline (message_index 0) →
        # nothing before it to fold
        ok = await app._compact_to(q1["message_index"])
        await pilot.pause()
        assert ok is False and called["n"] == 0
