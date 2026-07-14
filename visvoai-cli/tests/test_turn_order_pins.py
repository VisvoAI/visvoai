"""Step-0 pins for the agent_turn split: the ORDERING invariants the braid
guarantees today, asserted explicitly so a pure-move refactor cannot silently
reorder them. These ran green against the pre-split code — they are the truth
being preserved, not new behavior.

Pinned sequence for one tool-calling turn:
  1. the HUMAN message is on disk BEFORE the graph starts streaming (crash-safety)
  2. the pre_batch UNDO POINT is recorded BEFORE the tool-calling AIMessage is
     appended (rewind lands before the batch, and re-plans)
  3. messages persist in conversation order: Human → AI(tool_calls) → Tool → AI
"""
import pytest

from visvoai.cli import VisvoApp, agent, store


class _Chunk:
    def __init__(self, content):
        self.content = content


def _events():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    ai_call = AIMessage(content="", tool_calls=[{
        "name": "read_file", "id": "t1", "args": {"path": "x.py"}}])
    tool_msg = ToolMessage(content="contents", tool_call_id="t1", name="read_file")
    final = AIMessage(content="done")
    return [
        {"event": "on_chat_model_stream",
         "data": {"chunk": _Chunk([{"type": "text", "text": "…"}])}},
        {"event": "on_chat_model_end", "data": {"output": ai_call}},
        {"event": "on_tool_start", "name": "read_file", "run_id": "r1",
         "data": {"input": {"path": "x.py"}}},
        {"event": "on_tool_end", "run_id": "r1",
         "data": {"output": tool_msg}},
        {"event": "on_chat_model_end", "data": {"output": final}},
        {"event": "on_chain_end", "data": {"output": {"messages": [
            HumanMessage(content="hi"), ai_call, tool_msg, final]}}},
    ]


@pytest.mark.asyncio
async def test_turn_ordering_invariants(monkeypatch, tmp_path):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agent, "api_key_available", lambda m: True)

    log: list = []

    class _FakeGraph:
        async def astream_events(self, state, version="v2", config=None):
            log.append(("graph_started",))
            for ev in _events():
                yield ev

    monkeypatch.setattr(agent, "build_agent_graph", lambda *a, **k: _FakeGraph())

    real_append = store.append_branch_messages

    def spy_append(pid, cid, branch, messages):
        for m in messages:
            log.append(("append", m.__class__.__name__))
        return real_append(pid, cid, branch, messages)

    monkeypatch.setattr(store, "append_branch_messages", spy_append)

    app = VisvoApp()
    app._cwd = str(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        real_cp = app._record_checkpoint
        app._record_checkpoint = lambda idx, kind, label=None: (
            log.append(("checkpoint", kind)), real_cp(idx, kind, label))[1]
        await app._run_real_turn("hi")
        await pilot.pause()

    # 1 · crash-safety: the human message hit disk BEFORE streaming began
    assert log.index(("append", "HumanMessage")) < log.index(("graph_started",))

    # 2 · rewind correctness: the pre_batch undo point precedes the
    #     tool-calling AIMessage's persistence
    cp = log.index(("checkpoint", "pre_batch"))
    ai_appends = [i for i, e in enumerate(log) if e == ("append", "AIMessage")]
    assert cp < ai_appends[0]

    # 3 · persistence order mirrors conversation order
    seq = [name for kind, *rest in [e for e in log if e[0] == "append"]
           for name in rest]
    assert seq == ["HumanMessage", "AIMessage", "ToolMessage", "AIMessage"]
