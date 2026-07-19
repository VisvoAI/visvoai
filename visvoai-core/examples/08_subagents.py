"""Agents calling agents — a subagent is just a graph wrapped as a tool.

    pip install visvoai-core
    python 08_subagents.py                 # runs with NO api key (scripted models)

There is no special subagent API, and that's the point: an agent is a graph,
a tool is a function, so "call another agent" is a ~25-line helper that
builds a second graph and wraps it as a callable tool. The caller dispatches
it like any other tool; only the final answer comes back.

Shown here:
  · make_agent_tool()  — the helper you'd copy into your product
  · a "researcher" subagent with its OWN system prompt and OWN tools
  · the depth cap     — the subagent's tool list simply doesn't include the
                        dispatch tool, so it can never recurse (the same
                        trick our CLI uses: capability comes from the tool
                        list, not from trust in the model's judgment)
"""
import asyncio


# ── the helper: an agent, wrapped as a tool ──────────────────────────────────
def make_agent_tool(name, description, model, tools, system_prompt):
    """Wrap a whole agent as one callable tool. The caller's model sees a
    normal tool named `name`; invoking it runs a fresh, isolated conversation
    on its own graph and returns only the final answer."""
    from visvoai.core import ask
    from visvoai.core.runtime import AgentRuntime

    graph = AgentRuntime().build_graph(
        model=model, core_tools=tools, system_prompt=system_prompt)

    async def agent_tool(task: str) -> str:
        return await ask(graph, task)

    agent_tool.__name__ = name
    agent_tool.__doc__ = description
    return agent_tool


# ── the subagent's own tool ──────────────────────────────────────────────────
def lookup(topic: str) -> str:
    """Look a topic up in the knowledge base."""
    return {"step caps": "step caps force one clean final answer at a depth limit",
            }.get(topic, f"no entry for {topic!r}")


# ── two scripted models so this runs keyless (same graphs, same code) ────────
def scripted(script):
    from typing import ClassVar
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )

    class M(FakeMessagesListChatModel):
        queue: ClassVar[list] = list(script)   # shared with bound clones
        def bind_tools(self, tools): return self
        async def ainvoke(self, m, *a, **k): return type(self).queue.pop(0)
    return M(responses=[])


async def main():
    from langchain_core.messages import AIMessage
    from visvoai.core.runtime import AgentRuntime

    researcher_model = scripted([
        AIMessage(content="", tool_calls=[{"name": "lookup", "id": "r1",
                                           "args": {"topic": "step caps"}}]),
        AIMessage(content="Step caps force one clean final answer at a depth limit."),
    ])
    lead_model = scripted([
        AIMessage(content="", tool_calls=[{"name": "researcher", "id": "l1",
                  "args": {"task": "what do step caps do in agent loops?"}}]),
        AIMessage(content="Per my researcher: step caps guarantee a clean "
                          "final answer instead of a recursion error."),
    ])

    researcher = make_agent_tool(
        name="researcher",
        description="Delegate a research task; returns a written answer.",
        model=researcher_model,
        tools=[lookup],                  # ← no dispatch tool in here = depth cap
        system_prompt="You are a precise researcher. Use lookup; cite what you find.",
    )

    lead = AgentRuntime().build_graph(
        model=lead_model,
        core_tools=[researcher],         # the subagent, dispatched like any tool
        system_prompt="You are the lead. Delegate research; synthesize answers.",
    )

    from visvoai.core import ask
    print("lead's answer:",
          await ask(lead, "explain step caps — ask research if unsure"))


if __name__ == "__main__":
    asyncio.run(main())
