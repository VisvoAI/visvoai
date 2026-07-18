# visvoai-core

**The VisvoAI™ agent↔tools loop on LangGraph, done right — the ~1k lines every agent
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

Core is provider-agnostic — it takes any LangChain `BaseChatModel` (core itself never needs an API key; the model you pass in carries its own — e.g. `GEMINI_API_KEY` via visvoai-ai). Pair it
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
    core_tools=tools,                      # all_tools_map now optional
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

## Defining tools — four ways, pick per tool

`build_graph` takes them all, mixed freely; normalization to the loop's
internal currency happens once at the boundary, never in your files.

**1 · A plain typed function** — schema from type hints, description from
the docstring; a Google-style `Args:` section becomes per-argument
descriptions in the schema the model sees. No framework imports; async
works the same way.

```python
def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())

def fetch_status(url: str, timeout: int = 10) -> str:
    """Check whether a URL is up.

    Args:
        url: The full URL to probe, including scheme.
        timeout: Seconds to wait before giving up.
    """
    ...

graph = AgentRuntime().build_graph(model=model, core_tools=[word_count],
                                   system_prompt="You are ...")
```

**2 · The lifecycle class** — for tools that want declared config,
auto-registration, and persistence hooks (start→complete/error recorded in
*your* datastore via `ToolPersistence`; the default is a no-op):

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

Pass the class (or an instance) straight into `core_tools` — execution runs
through the full lifecycle. This is the same pattern the CLI and a hosted
platform build their internal tools on.

**3 · Anything LangChain** — already have `@tool` functions or
`StructuredTool`s? They pass through untouched, and every LangChain
integration ever written is usable as-is.

**4 · MCP servers** — out-of-process tools in any language; connect them at
the consumer layer (the CLI ships this: `visvoai mcp add ...`).

Mix them in one list; `as_tool` / `as_tools_map` are exported if you need
the normalization yourself:

```python
from visvoai.core import as_tools_map
tools = [word_count, EchoTool, some_langchain_tool]
graph = AgentRuntime().build_graph(model=model, core_tools=tools,
                                   system_prompt="You are ...")
```

## The extension seams

Everything is subclass + inject; there is nothing to fork.

| Seam | Override to get |
|---|---|
| `AgentRuntime._extend_graph()` | extra graph nodes — approval gates, background tasks, custom routers |
| `AgentRuntime._build_agent_node()` | your own model-calling node (e.g. per-turn assembled system prompts) |
| `AgentRuntime._get_checkpointer()` | durable graph state (any LangGraph checkpointer) |
| `AgentRuntime._get_interrupt_nodes()` | human-in-the-loop interrupt points |
| `RuntimeContext` (subclass) | your state carried to every tool — auth, sessions, registries |
| `AgentState` (TypedDict inheritance) + `_get_state_class()` | your fields in the graph state |
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
