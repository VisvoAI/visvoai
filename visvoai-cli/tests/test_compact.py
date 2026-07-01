"""Real /compact: cut-point logic (never splits a turn) + the flow actually folds the
older prefix into a summary, rewrites the thread, realigns receipts, and resets the
rewind floor — using a stubbed summarizer (no live model)."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from visvoai.cli import VisvoApp, agent, store
from visvoai.cli.commands import _compaction_cut
from visvoai.cli.checkpoints import ShadowRepo


def _tc(id):
    return {"name": "read_file", "args": {"path": "a"}, "id": id, "type": "tool_call"}


def test_cut_none_when_too_few_turns():
    msgs = [HumanMessage(content="q1"), AIMessage(content="a1"),
            HumanMessage(content="q2"), AIMessage(content="a2")]
    assert _compaction_cut(msgs, keep_turns=2) is None      # exactly 2 turns → nothing to fold


def test_cut_falls_on_a_human_boundary_keeping_last_turns():
    msgs = [HumanMessage(content="q1"), AIMessage(content="a1"),      # 0,1
            HumanMessage(content="q2"), AIMessage(content="a2"),      # 2,3
            HumanMessage(content="q3"), AIMessage(content="a3")]      # 4,5
    cut = _compaction_cut(msgs, keep_turns=2)
    assert cut == 2                                          # keep turns q2,q3; fold q1
    assert msgs[cut].__class__.__name__ == "HumanMessage"   # never mid-turn


def test_cut_does_not_split_a_tool_turn():
    msgs = [HumanMessage(content="q1"), AIMessage(content="", tool_calls=[_tc("1")]),
            ToolMessage(content="r", tool_call_id="1"), AIMessage(content="a1"),
            HumanMessage(content="q2"), AIMessage(content="a2"),
            HumanMessage(content="q3"), AIMessage(content="a3")]
    cut = _compaction_cut(msgs, keep_turns=2)
    assert msgs[cut].__class__.__name__ == "HumanMessage" and msgs[cut].content == "q2"


@pytest.mark.asyncio
async def test_compact_flow_folds_prefix_and_rewrites_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    monkeypatch.setattr(agent, "summarize_history",
                        lambda *a, **k: _async("SUMMARY: goal was X; edited a.py"))
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        store.ensure_branch(app._project_id, app._conv_id, "main")
        # 4 turns of history + 4 receipts
        for i in range(1, 5):
            app._history += [HumanMessage(content=f"q{i}"), AIMessage(content=f"a{i}")]
            store.append_branch_receipt(app._project_id, app._conv_id, "main",
                                        {"seconds": 1, "model": "m", "cost": 0.1})
        store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)
        app._persisted_count = 8

        await app._compact_flow()
        await pilot.pause()

        # older turns folded → [summary] + last 2 turns (4 msgs) = 5 messages
        assert len(app._history) == 5
        assert isinstance(app._history[0], SystemMessage)
        assert "SUMMARY" in app._history[0].content
        assert app._history[1].content == "q3"        # kept tail starts at turn 3
        # persisted thread matches
        assert store.load_branch_thread(app._project_id, app._conv_id, "main") == app._history
        # receipts realigned to the 2 kept turns
        assert len(store.read_branch_receipts(app._project_id, app._conv_id, "main")) == 2
        # gauge updated to a real (non-None) value
        assert app._ctx_pct is not None


@pytest.mark.asyncio
async def test_compact_noop_when_too_little(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    called = {"n": 0}
    async def _spy(*a, **k):
        called["n"] += 1; return "x"
    monkeypatch.setattr(agent, "summarize_history", _spy)
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        app._history = [HumanMessage(content="q1"), AIMessage(content="a1")]   # 1 turn
        await app._compact_flow()
        await pilot.pause()
        assert called["n"] == 0                        # never called the summarizer
        assert len(app._history) == 2                  # untouched


@pytest.mark.asyncio
async def test_compact_leaves_thread_when_summary_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    monkeypatch.setattr(agent, "summarize_history", lambda *a, **k: _async(None))
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        for i in range(1, 5):
            app._history += [HumanMessage(content=f"q{i}"), AIMessage(content=f"a{i}")]
        await app._compact_flow()
        await pilot.pause()
        assert len(app._history) == 8                  # summary failed → unchanged


async def _async(value):
    return value


@pytest.mark.asyncio
@pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")
async def test_compact_resets_rewind_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    monkeypatch.setattr(agent, "summarize_history", lambda *a, **k: _async("SUMMARY"))
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(proj)
        app._project_id = store.resolve_project_id(str(proj))
        app._conv_id = store.new_conversation_id()
        app._maybe_baseline()
        for i in range(1, 5):
            app._history += [HumanMessage(content=f"q{i}"), AIMessage(content=f"a{i}")]
            app._record_checkpoint(len(app._history), "turn", f"q{i}")
        store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)

        await app._compact_flow()
        await pilot.pause()

        rows = store.read_timeline(app._project_id, app._conv_id, "main")
        assert len(rows) == 1 and rows[0]["kind"] == "compact"      # floor reset
        assert rows[0]["message_index"] == len(app._history)
        assert app._cp_tip_id == rows[0]["checkpoint_id"]
