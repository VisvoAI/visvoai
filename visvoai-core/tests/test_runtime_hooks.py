"""The extension seams: every AgentRuntime hook, RuntimeContext, AgentState.

Each test is the seam's contract from a CONSUMER's seat: subclass, override,
build — and the override is honored without touching build_graph. This is the
promise the README makes ("no forks — subclass + inject"); here it's pinned.
"""
from typing import ClassVar, List, Optional

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END

from visvoai.core.context import RuntimeContext
from visvoai.core.runtime import AgentRuntime
from visvoai.core.state import AgentState


class _Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools):
        return self


@tool
def probe(x: str) -> str:
    """Probe."""
    return f"probe:{x}"


def _build(runtime, responses, tools=None, **kw):
    tools = tools if tools is not None else [probe]
    return runtime.build_graph(
        model=_Fake(responses=responses), core_tools=tools,
        all_tools_map={t.name: t for t in tools},
        system_prompt="seam test", **kw)


# ── _extend_graph: add your own node ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_extend_graph_adds_a_reachable_node():
    """A consumer node added in _extend_graph participates in the run when its
    routing sends flow there — the platform's HITL/background nodes in
    miniature."""
    visits: List[str] = []

    class AuditRuntime(AgentRuntime):
        def _extend_graph(self, workflow, tool_configs):
            async def audit(state: AgentState):
                visits.append("audit")
                return {}
            workflow.add_node("audit", audit)
            workflow.add_edge("audit", "agent")

        def _tools_routing(self, tool_configs):
            return (lambda state: "audit"), {"audit": "audit", "agent": "agent"}

    g = _build(AuditRuntime(), [
        AIMessage(content="", tool_calls=[{"name": "probe", "args": {"x": "a"},
                                           "id": "c1"}]),
        AIMessage(content="done")])
    out = await g.ainvoke({"messages": [HumanMessage(content="go")]})
    assert visits == ["audit"]                 # tools → audit → agent → END
    assert out["messages"][-1].content == "done"


# ── _build_agent_node: replace the model-calling node ────────────────────────

@pytest.mark.asyncio
async def test_build_agent_node_override_and_ctx_contents():
    """The CLI's per-turn context assembly seam: the override receives a
    GraphBuildContext carrying exactly the build inputs, and its node body
    replaces call_model entirely."""
    seen = {}

    class PromptRuntime(AgentRuntime):
        def _build_agent_node(self, ctx):
            seen["system_prompt"] = ctx.system_prompt
            seen["tool_names"] = sorted(ctx.all_tools_map)
            seen["max_steps"] = ctx.max_agent_steps

            async def node(state: AgentState):
                return {"messages": [AIMessage(content="from custom node")]}
            return node

    g = _build(PromptRuntime(), [AIMessage(content="never used")])
    out = await g.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert out["messages"][-1].content == "from custom node"
    assert seen["system_prompt"] == "seam test"
    assert seen["tool_names"] == ["probe"]
    assert seen["max_steps"] is not None       # default cap flows into ctx


# ── _agent_routing: replace the after-agent decision ─────────────────────────

@pytest.mark.asyncio
async def test_agent_routing_override():
    class ShortCircuit(AgentRuntime):
        def _agent_routing(self, ctx):
            # send EVERYTHING to END — even tool calls (a kill-switch consumer)
            return (lambda state: END), {END: END, "tools": "tools"}

    g = _build(ShortCircuit(), [
        AIMessage(content="", tool_calls=[{"name": "probe", "args": {"x": "a"},
                                           "id": "c1"}])])
    out = await g.ainvoke({"messages": [HumanMessage(content="go")]})
    assert len(out["messages"]) == 2           # tool call never executed


# ── checkpointer + interrupts ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpointer_hook_enables_multi_turn_state():
    from langgraph.checkpoint.memory import MemorySaver

    class Durable(AgentRuntime):
        def _get_checkpointer(self, checkpointer=None):
            return MemorySaver()

    g = _build(Durable(), [AIMessage(content="turn one"),
                           AIMessage(content="turn two")])
    cfg = {"configurable": {"thread_id": "t1"}}
    await g.ainvoke({"messages": [HumanMessage(content="first")]}, config=cfg)
    out = await g.ainvoke({"messages": [HumanMessage(content="second")]}, config=cfg)
    # the checkpointer carried turn one's messages into turn two's state
    contents = [m.content for m in out["messages"]]
    assert contents == ["first", "turn one", "second", "turn two"]


@pytest.mark.asyncio
async def test_interrupt_nodes_pause_the_graph():
    from langgraph.checkpoint.memory import MemorySaver

    class Gated(AgentRuntime):
        def _extend_graph(self, workflow, tool_configs):
            async def gate(state: AgentState):
                return {}
            workflow.add_node("gate", gate)
            workflow.add_edge("gate", "agent")

        def _tools_routing(self, tool_configs):
            return (lambda state: "gate"), {"gate": "gate", "agent": "agent"}

        def _get_checkpointer(self, checkpointer=None):
            return MemorySaver()

        def _get_interrupt_nodes(self):
            return ["gate"]                    # pause BEFORE the gate runs

    g = _build(Gated(), [
        AIMessage(content="", tool_calls=[{"name": "probe", "args": {"x": "a"},
                                           "id": "c1"}]),
        AIMessage(content="resumed")])
    cfg = {"configurable": {"thread_id": "t1"}}
    out = await g.ainvoke({"messages": [HumanMessage(content="go")]}, config=cfg)
    # paused at the interrupt: the tool ran, the final answer has NOT happened
    assert not any(m.content == "resumed" for m in out["messages"])
    resumed = await g.ainvoke(None, config=cfg)      # approve → continue
    assert resumed["messages"][-1].content == "resumed"


# ── RuntimeContext + AgentState extension ────────────────────────────────────

def test_runtime_context_subclass_carries_consumer_state():
    from dataclasses import dataclass, field

    @dataclass
    class MyContext(RuntimeContext):
        user_id: str = "u1"
        scratch: dict = field(default_factory=dict)

    ctx = MyContext(user_id="alice")
    assert isinstance(ctx, RuntimeContext)
    ctx.scratch["k"] = "v"
    assert ctx.user_id == "alice"


@pytest.mark.asyncio
async def test_agent_state_extension_fields_flow_through_the_graph():
    class MyState(AgentState):
        approval_pending: bool

    class Stateful(AgentRuntime):
        def _get_state_class(self):
            return MyState

        def _build_agent_node(self, ctx):
            async def node(state):
                # consumer fields ride the same state dict as messages
                flag = state.get("approval_pending", False)
                return {"messages": [AIMessage(content=f"pending={flag}")]}
            return node

    g = _build(Stateful(), [])
    out = await g.ainvoke({"messages": [HumanMessage(content="go")],
                           "approval_pending": True})
    assert out["messages"][-1].content == "pending=True"
