<p align="center"><img src="https://raw.githubusercontent.com/VisvoAI/visvoai/main/assets/icon.png" alt="VisvoAI" width="90"></p>

# visvoai-core

[![tests](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml/badge.svg)](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml) [![PyPI](https://img.shields.io/pypi/v/visvoai-core.svg)](https://pypi.org/project/visvoai-core/) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)

**The VisvoAI™ agent↔tools loop on LangGraph, done right — the ~1k lines every agent
product ends up writing, already hardened by two real consumers.**

An AI agent is a loop — the model thinks, calls a tool, reads the result,
thinks again, and finally answers. Writing that loop well is surprisingly
hard: endless loops, repeated calls, messy endings. `visvoai-core` is that
loop, written once and written well, with clean hooks to plug in your own
tools, storage, and rules.

It is deliberately *not* a framework — no datastore, no web layer, no auth.
The same code carries a full terminal agent
([`visvoai-cli`](https://pypi.org/project/visvoai-cli/)) and a hosted
platform, so the hooks you'd use are the hooks we use.

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
    core_tools=tools,
    system_prompt="You are a code assistant.",
)

# a standard LangGraph app — invoke it, or stream events for a live UI
# inside an async function (or asyncio.run(...) — see examples/01)
from visvoai.core import ask
answer = await ask(graph, "What's in pyproject.toml?")
print(result["messages"][-1].content)
```

**Building a product on this?** [BUILD-YOUR-OWN.md](./BUILD-YOUR-OWN.md) is
the whole recipe — the four decisions, a Slack-bot skeleton, and which hook
to override when the defaults aren't enough.

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

Want approval gates? A Postgres audit trail? Your own state fields? Each
is one override — these are the same hooks our CLI and platform use:

Everything is subclass + inject; there is nothing to fork.

| Seam | Override to get |
|---|---|
| `AgentRuntime._extend_graph()` | extra graph nodes — approval gates, background tasks, custom routers |
| `AgentRuntime._build_agent_node()` | your own model-calling node (e.g. per-turn assembled system prompts) |
| `AgentRuntime._get_checkpointer()` | durable graph state — a checkpointer is LangGraph's saved-state store, what gives the agent memory across turns |
| `AgentRuntime._get_interrupt_nodes()` | human-in-the-loop interrupt points |
| `RuntimeContext` (subclass) | your state carried to every tool — auth, sessions, registries |
| `AgentState` (TypedDict inheritance) + `_get_state_class()` | your fields in the graph state |
| `ToolPersistence` (implement) | tool-call records in your datastore |
| `LLMPersistence` (implement) | per-call model usage/cost records |

This is exactly how the two real consumers differ: the CLI overrides the
agent node for per-turn context assembly; the hosted platform adds HITL and
background-task nodes, a Postgres persistence pair, and an auth-carrying
context — same runtime, no forks.

## Migrating from LangChain

Incremental, by design: your existing `@tool` functions and `StructuredTool`s
pass into `build_graph(core_tools=[...])` untouched, and any `BaseChatModel`
you already construct works as the model. Migrate the loop first (keep your
tools), then simplify tools to plain functions at your own pace. Nothing to
rewrite on day one.

## When *not* to use this

If you want hundreds of integrations, chains, and a batteries ecosystem, use
LangChain/LangGraph directly — that's what they're for. `visvoai-core` is for
when you're building a *product* on the loop and want the sharp edges
(recursion deaths, runaway rounds, tool sprawl, lifecycle plumbing) already
filed down.

## Examples

**[`examples/07_everything_together.py`](./examples/07_everything_together.py)**
is a whole product in 180 lines — retrieval choosing tools, memory resolving
"restart *it*", an audit row appearing in SQLite — and it runs with **no API
key**. The [examples ladder](./examples/) then takes each idea one file at a
time, four of them keyless.

## License

MIT
