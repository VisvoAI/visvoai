# Build your own agent product on visvoai-core

You want a Slack bot, a web app, an internal CLI, a review robot — anything
with an agent inside. This page is the whole recipe. Every piece links to a
runnable example.

## What you actually have to build

Four decisions. Everything else is provided.

| # | Decision | Effort | Where to look |
|---|---|---|---|
| 1 | **Which model** | one line | `build_chat_model("gemini:gemini-2.5-flash")` — or pick by price/facts from the registry ([ai example 02](../visvoai-ai/examples/02_choose_and_meter.py)) |
| 2 | **Which tools** | plain functions | write Python functions with docstrings; mix in lifecycle classes or LangChain tools ([core example 03](./examples/03_creating_tools.py)) |
| 3 | **How output reaches your users** | one async loop | `graph.astream_events(...)` yields text chunks, tool starts, tool results — print them, push them to Slack, stream them over SSE ([core example 02](./examples/02_streaming_events.py)) |
| 4 | **What gets remembered / recorded** | optional | a checkpointer for multi-turn memory, a `ToolPersistence` for an audit trail ([core example 06](./examples/06_sqlite_audit_trail.py)) |

Wire the four together and you have a product. [Example 07](./examples/07_everything_together.py)
is exactly that wiring in 180 lines — copy it and replace the fake tools
with your real ones.

## The skeleton (a Slack bot, for concreteness)

```python
from visvoai.ai import build_chat_model
from visvoai.core.runtime import AgentRuntime
from langgraph.checkpoint.memory import MemorySaver

def search_docs(query: str) -> str:
    """Search the company docs and return the top matches."""
    ...

def file_ticket(title: str, body: str) -> str:
    """File a ticket in the tracker and return its URL."""
    ...

graph = AgentRuntime().build_graph(
    model=build_chat_model("gemini:gemini-2.5-flash"),
    core_tools=[search_docs, file_ticket],
    system_prompt="You are our helpdesk bot. Search before you answer.",
    checkpointer=MemorySaver(),          # one conversation per Slack thread
)

async def on_slack_message(channel_thread: str, text: str):
    config = {"configurable": {"thread_id": channel_thread}}
    async for ev in graph.astream_events(
            {"messages": [("user", text)]}, config, version="v2"):
        if ev["event"] == "on_chat_model_stream":
            append_to_slack_draft(ev["data"]["chunk"].content)
        elif ev["event"] == "on_tool_start":
            post_status(f"⚙ {ev['name']}…")
```

For request/response surfaces (no streaming), skip the event loop entirely:
`answer = await ask(graph, text, thread_id=channel_thread)` — text in, text
out.

The `thread_id` is the entire memory story: same id → the agent remembers
the conversation; new id → fresh start. Swap `MemorySaver` for a Postgres or
SQLite checkpointer when you need memory to survive restarts.

## When the defaults aren't enough

The loop itself is changeable — subclass `AgentRuntime` and override only
what you need. Each hook is one method:

| You want… | Override |
|---|---|
| an approval step before dangerous tools run | `_extend_graph` (add a node) + `_get_interrupt_nodes` (pause there) |
| your own routing after the agent thinks | `_agent_routing` |
| extra state fields flowing through the graph | `_get_state_class` |
| a different agent or tools node entirely | `_build_agent_node` / `_build_tools_node` |
| memory stored your way | `_get_checkpointer` |

All seven hooks with working code: [example 04](./examples/04_extend_the_runtime.py).
These are not theoretical — our own terminal agent
([visvoai-cli](https://pypi.org/project/visvoai-cli/)) and a hosted platform
(closed-source, not in this repo) are both built on exactly these overrides.

## Scaling worries, pre-answered

- **"I'll have hundreds of tools"** — index them once, bind only what
  matches each request: [example 05](./examples/05_tool_retrieval.py).
- **"I need to see everything my agent ever did"** — four persistence
  methods, injected once: [example 06](./examples/06_sqlite_audit_trail.py).
- **"Can my agent call other agents?"** — yes: a subagent is a second graph
  wrapped as a tool, ~25 lines, recursion made impossible by construction:
  [example 08](./examples/08_subagents.py).
- **"The model might loop forever"** — it can't: the step cap forces one
  clean, tool-free final answer. Built in, nothing to configure.

## Forking instead of depending

MIT-licensed — forking is legitimate. Before you do: most "I need to change
core" cases are covered by the hooks above, and staying a dependency means
you keep receiving fixes. Fork when you need to change the loop's *shape* in
ways the hooks don't reach — and if that's the case, we'd genuinely like to
hear why in [an issue](https://github.com/VisvoAI/visvoai/issues/new/choose)
first; it may be the next hook.
