"""Launcher flags — --model / --resume startup behavior + graceful fallback.

A bad model reverts to the default with a notice; a missing/unknown conversation
starts fresh; valid values are honored.
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp
from visvoai.cli import agent, store
from visvoai.cli.widgets import Assistant, UserMsg


def test_valid_model_is_used():
    valid = agent.chat_models()[1][0]
    app = VisvoApp(model=valid)
    assert app._model == valid
    assert app._startup_notices == []


def test_unknown_model_reverts_with_notice():
    app = VisvoApp(model="totally-not-a-model")
    assert app._model == agent.default_chat_model()
    assert app._startup_notices and "totally-not-a-model" in app._startup_notices[0]


@pytest.mark.asyncio
async def test_resume_valid_replays(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    pid = store.resolve_project_id(str(proj))
    store.save_conversation(pid, "good123",
                            [HumanMessage(content="hi"), AIMessage(content="hello")])

    app = VisvoApp(resume="good123")
    app._cwd = str(proj)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app._conv_id == "good123":
                break
        assert app._conv_id == "good123"
        assert len(app._history) == 2
        assert app.query(UserMsg)


@pytest.mark.asyncio
async def test_resume_replays_list_content_ai_reply(tmp_path, monkeypatch):
    """An AI reply stored as list-of-blocks (Gemini/Claude) must still render on
    resume — the regression that left resumed threads looking blank."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    pid = store.resolve_project_id(str(proj))
    store.save_conversation(pid, "blocks1", [
        HumanMessage(content="Hi"),
        AIMessage(content=[{"type": "text", "text": "Hello there!"}]),
    ])
    app = VisvoApp(resume="blocks1")
    app._cwd = str(proj)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app._conv_id == "blocks1":
                break
        assert app.query(UserMsg)              # user turn rendered
        assert len(app.query(Assistant)) == 1  # AI reply rendered (not dropped)


@pytest.mark.asyncio
async def test_resume_replays_full_trace(tmp_path, monkeypatch):
    """Resume rebuilds the whole turn — reasoning, tool call + result, answer —
    not just the final answer (all persisted in the message thread)."""
    from langchain_core.messages import ToolMessage
    from visvoai.cli.widgets import Thinking
    from visvoai.cli.widgets.tool_row import ToolNode
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    pid = store.resolve_project_id(str(proj))
    store.append_messages(pid, "trace1", [
        HumanMessage(content="fix the bug"),
        AIMessage(content=[{"type": "thinking", "thinking": "look at the file"},
                           {"type": "text", "text": "Reading it."}],
                  tool_calls=[{"name": "read_file", "args": {"path": "a.py"}, "id": "t1"}]),
        ToolMessage(content="1\tdef foo(): pass", tool_call_id="t1"),
        AIMessage(content="Fixed it."),
    ])
    app = VisvoApp(resume="trace1")
    app._cwd = str(proj)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app._conv_id == "trace1":
                break
        assert len(app.query(Thinking)) == 1     # reasoning restored
        assert len(app.query(ToolNode)) == 1     # tool call + result restored
        assert len(app.query(Assistant)) == 2    # the 'Reading it.' step + final answer


@pytest.mark.asyncio
async def test_resume_restores_receipt_footer_and_cost(tmp_path, monkeypatch):
    """A saved per-turn receipt restores the footer + thinking duration + cost on resume."""
    from visvoai.cli.widgets import Thinking, TurnFooter
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir()
    pid = store.resolve_project_id(str(proj))
    store.append_messages(pid, "r1", [
        HumanMessage(content="fix bug"),
        AIMessage(content=[{"type": "thinking", "thinking": "looking"},
                           {"type": "text", "text": "Done."}]),
    ])
    store.append_receipt(pid, "r1", {
        "seconds": 4.2, "model": "gemini:gemini-3-flash-preview", "model_name": "Gemini 3 Flash",
        "thinking_level": "medium", "thinking_durations": [3.0],
        "input_tokens": 1200, "output_tokens": 300, "context_tokens": 1200, "cost": 0.0012,
    })
    app = VisvoApp(resume="r1"); app._cwd = str(proj)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app._conv_id == "r1":
                break
        assert "Thought for" in str(app.query(Thinking).first().render())   # duration restored
        assert len(app.query(TurnFooter)) == 1                              # receipt footer restored
        assert "~$0.0012" in str(app.query(TurnFooter).first().render())
        assert app._conv_cost == 0.0012                                     # cost summed


@pytest.mark.asyncio
async def test_resume_unknown_starts_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    app = VisvoApp(resume="does-not-exist")
    app._cwd = str(proj)
    async with app.run_test() as pilot:
        for _ in range(20):
            await pilot.pause()
        assert app._conv_id is None
        assert app._history == []
