# visvoai-core

**The agent↔tools loop on LangGraph, done right — the ~1k lines every agent
product ends up writing, already hardened by two real consumers.**

`visvoai-core` is deliberately not a framework. It's a thin, opinionated
runtime: the loop, a tool lifecycle, semantic tool retrieval, and extension
seams that are proven — the same seams carry a full-featured terminal agent
([`visvoai-cli`](https://pypi.org/project/visvoai-cli/)) and a hosted
multi-tenant platform. No datastore, web, or auth dependencies; you subclass
and inject what you need.

```bash
pip install visvoai-core          # pulls langgraph + langchain-core only
```

Core is provider-agnostic — it takes any LangChain `BaseChatModel`. Pair it
with [`visvoai-ai`](https://pypi.org/project/visvoai-ai/) for a unified
provider layer, or bring your own model.

## Sixty seconds to a working agent

```python
from visvoai.core.runtime import AgentRuntime
from visvoai.ai import build_chat_model            # pip install "visvoai-ai[gemini]"
from langchain_core.tools import tool

@tool
def read_file(path: str) -> str:
    """Read a file and return its contents."""
    return open(path).read()

tools = [read_file]
graph = AgentRuntime().build_graph(
    model=build_chat_model("gemini:gemini-2.5-flash"),
    core_tools=tools,
    all_tools_map={t.name: t for t in tools},
    system_prompt="You are a code assistant.",
)

# a standard LangGraph app — invoke it, or stream events for a live UI
result = await graph.ainvoke({"messages": [("user", "What's in pyproject.toml?")]})
print(result["messages"][-1].content)
```

## What the loop gives you that raw LangGraph doesn't

- **A soft step cap with clean finalize** — at the budget, the model is
  re-invoked *without* tools and instructed to answer. Your users get a
  coherent final message instead of a `GraphRecursionError`.
- **Duplicate-call blocking** — the model can't burn rounds re-issuing the
  identical tool call.
- **Semantic tool retrieval** — when you have too many tools to bind at all
  (MCP fleets, plugin ecosystems), `find_tools` + per-round retrieval bind
  only what's relevant to the current request.
- **A tool lifecycle, not just functions** — declare config, write
  `_execute()`, and registration/validation/persistence hooks come free.

## Writing a tool

Plain LangChain `@tool` functions work as-is. For tools that want the
lifecycle (config, registration, persistence), subclass:

```python
from pydantic import BaseModel
from visvoai.core.tools import BaseAgentTool, tool_config
from visvoai.core.results import ToolResult

class EchoArgs(BaseModel):
    text: str

@tool_config(is_core=True, routing_hint="Use to echo text back.")
class EchoTool(BaseAgentTool):
    name = "echo"
    description = "Echo the input back."
    args_schema = EchoArgs

    def _execute(self, tool_call_id: str, **kwargs):
        return ToolResult.success(self.name, kwargs["text"])
```

Tools auto-register at class-definition time. `execute()` ships a default
start→run→complete/error lifecycle; inject a `ToolPersistence` implementation
to record those events in *your* datastore — the default is a no-op, so tools
run standalone.

## The extension seams

Everything is subclass + inject; there is nothing to fork.

| Seam | Override to get |
|---|---|
| `AgentRuntime._extend_graph()` | extra graph nodes — approval gates, background tasks, custom routers |
| `AgentRuntime._build_agent_node()` | your own model-calling node (e.g. per-turn assembled system prompts) |
| `AgentRuntime._get_checkpointer()` | durable graph state (any LangGraph checkpointer) |
| `AgentRuntime._get_interrupt_nodes()` | human-in-the-loop interrupt points |
| `RuntimeContext` (subclass) | your state carried to every tool — auth, sessions, registries |
| `AgentState` (TypedDict inheritance) | your fields in the graph state |
| `ToolPersistence` (implement) | tool-call records in your datastore |
| `LLMPersistence` (implement) | per-call model usage/cost records |

This is exactly how the two real consumers differ: the CLI overrides the
agent node for per-turn context assembly; the hosted platform adds HITL and
background-task nodes, a Postgres persistence pair, and an auth-carrying
context — same runtime, no forks.

## When *not* to use this

If you want hundreds of integrations, chains, and a batteries ecosystem, use
LangChain/LangGraph directly — that's what they're for. `visvoai-core` is for
when you're building a *product* on the loop and want the sharp edges
(recursion deaths, runaway rounds, tool sprawl, lifecycle plumbing) already
filed down.

## Examples

Six runnable, live-verified examples in [`examples/`](./examples/) — from a
20-line agent to every tool-creation style, retrieval at fleet scale, and a
real SQLite persistence implementation. Three run with no API key.

## License

MIT
