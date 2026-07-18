"""The core loop end-to-end: routing, step cap, system prompt, state flow.

These run entirely on fake models — no keys, no network. They are the
behavioral contract an adopter builds on: what the loop DOES, pinned.
"""
from typing import Any, ClassVar, List, Optional

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from visvoai.core.graph import DEFAULT_MAX_AGENT_STEPS, build_graph


class _Model(FakeMessagesListChatModel):
    """Fake chat model that records every invocation's messages and whether the
    invoked instance was tool-bound. All bound clones SHARE one response queue
    (class-level) — the graph alternates between bound clones and the unbound
    base for finalize, and per-instance counters would desync the script."""
    calls: ClassVar[list] = []          # (was_bound, messages) per ainvoke
    queue: ClassVar[list] = []
    bound: bool = False

    def bind_tools(self, tools):
        clone = _Model(responses=self.responses)
        clone.bound = True
        return clone

    async def ainvoke(self, messages, *a, **kw):
        _Model.calls.append((self.bound, list(messages)))
        return _Model.queue.pop(0)


@tool
def lookup(key: str) -> str:
    """Look up a value."""
    return f"value-of-{key}"


def _tool_call(name="lookup", args=None, cid="c1"):
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args or {"key": "x"}, "id": cid}])


def _graph(responses, **kw):
    _Model.calls = []
    _Model.queue = list(responses)
    model = _Model(responses=responses)
    tools = [lookup]
    return build_graph(model=model, core_tools=tools,
                       all_tools_map={t.name: t for t in tools},
                       system_prompt="You are a test agent.", **kw)


# ── the loop ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_round_then_answer():
    """agent → tools → agent → END, with the ToolMessage in between."""
    g = _graph([_tool_call(), AIMessage(content="done: value-of-x")])
    out = await g.ainvoke({"messages": [HumanMessage(content="get x")]})
    kinds = [m.__class__.__name__ for m in out["messages"]]
    assert kinds == ["HumanMessage", "AIMessage", "ToolMessage", "AIMessage"]
    tool_msg = out["messages"][2]
    assert isinstance(tool_msg, ToolMessage) and "value-of-x" in tool_msg.content
    assert out["messages"][-1].content == "done: value-of-x"


@pytest.mark.asyncio
async def test_no_tool_calls_ends_immediately():
    g = _graph([AIMessage(content="direct answer")])
    out = await g.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert len(out["messages"]) == 2
    assert out["messages"][-1].content == "direct answer"


@pytest.mark.asyncio
async def test_system_prompt_prepended_every_round():
    g = _graph([_tool_call(), AIMessage(content="ok")])
    await g.ainvoke({"messages": [HumanMessage(content="go")]})
    assert len(_Model.calls) == 2
    for _, messages in _Model.calls:
        assert isinstance(messages[0], SystemMessage)
        assert "test agent" in messages[0].content


@pytest.mark.asyncio
async def test_parallel_tool_calls_one_round():
    """Two calls in one AIMessage → both ToolMessages before the next round."""
    multi = AIMessage(content="", tool_calls=[
        {"name": "lookup", "args": {"key": "a"}, "id": "c1"},
        {"name": "lookup", "args": {"key": "b"}, "id": "c2"}])
    g = _graph([multi, AIMessage(content="both done")])
    out = await g.ainvoke({"messages": [HumanMessage(content="go")]})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert {m.content for m in tool_msgs} == {"value-of-a", "value-of-b"}


# ── the soft step cap ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_step_cap_forces_clean_finalize():
    """At the cap the loop runs ONE tool-free finalize round: the call is
    UNBOUND (tools physically absent) and carries the finalize instruction;
    a well-formed model answers and the graph ends cleanly."""
    script = [_tool_call(cid=f"c{i}") for i in range(3)]
    script.append(AIMessage(content="forced summary"))
    g = _graph(script, max_agent_steps=3)
    out = await g.ainvoke({"messages": [HumanMessage(content="loop!")]},
                          config={"recursion_limit": 100})
    assert out["messages"][-1].content == "forced summary"

    final_bound, final_msgs = _Model.calls[-1]
    assert final_bound is False                      # tools physically absent
    assert "maximum number of tool-using steps" in final_msgs[0].content
    ai_with_tools = [m for m in out["messages"]
                     if isinstance(m, AIMessage) and m.tool_calls]
    assert len(ai_with_tools) == 3                   # exactly cap rounds ran


@pytest.mark.asyncio
async def test_step_cap_ends_even_a_pathological_model():
    """A model that STILL emits tool calls in the unbound finalize round
    (hallucinated calls — malformed providers exist) is forced to END instead
    of looping to the recursion limit the cap exists to prevent."""
    forever = [_tool_call(cid=f"c{i}") for i in range(20)]
    g = _graph(forever, max_agent_steps=3)
    out = await g.ainvoke({"messages": [HumanMessage(content="loop!")]},
                          config={"recursion_limit": 100})
    # ended by force: cap rounds + the one pathological finalize attempt
    ai_msgs = [m for m in out["messages"] if isinstance(m, AIMessage)]
    assert len(ai_msgs) == 4
    assert len(_Model.queue) == 16                   # didn't drain the script


@pytest.mark.asyncio
async def test_step_cap_default_and_disable():
    assert DEFAULT_MAX_AGENT_STEPS == 10
    # None disables the guard: the model's 4 rounds run without finalize framing
    rounds = [_tool_call(cid=f"c{i}") for i in range(4)] + [AIMessage(content="end")]
    g = _graph(rounds, max_agent_steps=None)
    out = await g.ainvoke({"messages": [HumanMessage(content="go")]},
                          config={"recursion_limit": 50})
    assert out["messages"][-1].content == "end"
    assert all("maximum number" not in (m[1][0].content if m[1] else "")
               for m in _Model.calls)


# ── deferred binding via per-round retrieval ────────────────────────────────

@pytest.mark.asyncio
async def test_per_round_retrieval_binds_only_relevant_deferred():
    """Deferrable tools (in all_tools_map, not core) bind per round from the
    retriever; the ToolNode can still EXECUTE any tool in the map."""
    bound_sets: List[Any] = []

    class _Rec(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            bound_sets.append({t.name for t in tools})
            return self

    @tool
    def rare(key: str) -> str:
        """Rarely relevant."""
        return "rare!"

    model = _Rec(responses=[
        AIMessage(content="", tool_calls=[{"name": "rare", "args": {"key": "k"},
                                           "id": "c1"}]),
        AIMessage(content="done")])
    g = build_graph(model=model, core_tools=[lookup],
                    all_tools_map={"lookup": lookup, "rare": rare},
                    system_prompt="t",
                    per_round_retrieve=lambda q: ["rare"] if "rare" in q else [])
    out = await g.ainvoke({"messages": [HumanMessage(content="use the rare tool")]})
    assert any("rare!" in m.content for m in out["messages"]
               if isinstance(m, ToolMessage))
    assert {"lookup", "rare"} in bound_sets          # retrieved → bound that round


@pytest.mark.asyncio
async def test_retrieval_failure_is_non_fatal():
    def boom(q):
        raise RuntimeError("index down")

    @tool
    def extra(key: str) -> str:
        """Extra."""
        return "x"

    model = _Model(responses=[AIMessage(content="still fine")])
    _Model.calls = []
    _Model.queue = [AIMessage(content="still fine")]
    g = build_graph(model=model, core_tools=[lookup],
                    all_tools_map={"lookup": lookup, "extra": extra},
                    system_prompt="t", per_round_retrieve=boom)
    out = await g.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert out["messages"][-1].content == "still fine"
