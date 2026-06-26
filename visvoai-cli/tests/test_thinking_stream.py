"""Phase 4 — thinking chunks render into the Thinking widget.

classify_chunk splits a stream chunk into ('text'|'thinking', text); _run_real_turn
routes thinking → a collapsible Thinking block and text → the Assistant reply.
Deterministic: a fake graph yields canned thinking+text events (no network).
"""
import pytest

from visvoai.cli import VisvoApp
from visvoai.cli import agent
from visvoai.cli.widgets import Assistant, Thinking


class _Chunk:
    def __init__(self, content):
        self.content = content


def test_classify_chunk_text_and_thinking():
    assert list(agent.classify_chunk(_Chunk("hello"))) == [("text", "hello")]
    assert list(agent.classify_chunk(_Chunk([{"type": "thinking", "thinking": "r"}]))) == [("thinking", "r")]
    assert list(agent.classify_chunk(_Chunk([{"type": "text", "text": "a"}]))) == [("text", "a")]
    mixed = list(agent.classify_chunk(_Chunk([
        {"type": "thinking", "thinking": "reason"},
        {"type": "text", "text": "answer"},
    ])))
    assert mixed == [("thinking", "reason"), ("text", "answer")]


class _FakeGraph:
    """Yields a thinking chunk, then a text chunk, then the final state."""
    async def astream_events(self, state, version="v2", config=None):
        yield {"event": "on_chat_model_stream",
               "data": {"chunk": _Chunk([{"type": "thinking", "thinking": "let me think"}])}}
        yield {"event": "on_chat_model_stream",
               "data": {"chunk": _Chunk([{"type": "text", "text": "the answer"}])}}
        from langchain_core.messages import AIMessage, HumanMessage
        yield {"event": "on_chain_end",
               "data": {"output": {"messages": [HumanMessage(content="hi"), AIMessage(content="the answer")]}}}


@pytest.mark.asyncio
async def test_thinking_renders_then_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agent, "api_key_available", lambda model_id: True)
    monkeypatch.setattr(agent, "build_agent_graph", lambda *a, **k: _FakeGraph())

    app = VisvoApp()
    app._cwd = str(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app._run_real_turn("hi")
        await pilot.pause()
        thinks = app.query(Thinking)
        answers = app.query(Assistant)
        assert thinks, "a Thinking block should render for the reasoning chunk"
        assert answers, "an Assistant block should render for the text chunk"
        assert thinks.first()._active is False  # closed (done) once the answer started
