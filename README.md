# visvoai

Open-core Python packages for building agents — a clean, extensible agent runtime
and LLM layer you can `pip install` and build on.

```
visvoai-cli   →   visvoai-core   →   visvoai-ai
(a consumer)      (agent runtime)    (LLM provider layer)
```

Dependencies point one way only. Each package is usable on its own terms; nothing
here depends on any private or hosted infrastructure.

## Packages

| Package | What it is | Install |
|---------|------------|---------|
| **[visvoai-ai](./visvoai-ai)** | Unified multi-provider LLM access (Gemini, Anthropic, OpenAI + OpenAI-compatible). One facade per provider; a single source of truth for model facts. | `pip install "visvoai-ai[gemini]"` |
| **[visvoai-core](./visvoai-core)** | Extensible LangGraph agent runtime — the agent↔tools loop, a tool base class with auto-registration, semantic tool retrieval, and clean subclass/inject extension seams. No datastore, web, or auth deps. | `pip install visvoai-core` |
| **[visvoai-cli](./visvoai-cli)** | A developer-tool CLI built on `visvoai-core` — reads/edits files, runs shell commands, streams to stdout. Also the reference example of consuming the runtime. | `pip install visvoai-cli` |

## Design

The runtime is extended the same way by everyone — subclass the base classes and
inject your implementations. No forks, no patches:

- subclass **`AgentRuntime`** to add graph nodes, a checkpointer, or interrupt points
- subclass **`RuntimeContext`** to carry your own state to tools
- extend **`AgentState`** (TypedDict inheritance) to add state fields
- implement **`ToolPersistence`** to record tool calls wherever you want
- subclass **`BaseAgentTool`** / **`ToolResult`** for your own tool and result shapes

These same seams are what a full hosted agent platform builds on — the public
packages are the runtime, not the product.

## Quick start

```bash
pip install visvoai-cli
export GEMINI_API_KEY=...
visvoai "list the Python files in the current directory"
```

Or build your own agent on `visvoai-core` — see
[visvoai-core/README.md](./visvoai-core/README.md).

## License

MIT
