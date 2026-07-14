# VisvoAI

**A terminal coding agent with a trust model — and the Python runtime it's built on.**

```
visvoai-cli          the product: a TUI coding agent
     │               agents · skills · MCP · sandboxed shell · time-travel
     ▼
visvoai-core         the runtime: the agent↔tools loop, done right
     │               tool lifecycle · retrieval · extension seams
     ▼
visvoai-ai           the model layer: one interface, many providers
                     registry · thinking levels · cost · live catalog
```

Dependencies point one way only. Nothing here depends on any private or hosted
infrastructure — these packages *are* the runtime under a commercial platform,
published as they're used.

## The CLI

```bash
pip install visvoai-cli
export GEMINI_API_KEY=...        # or Anthropic, OpenAI, any OpenAI-compatible
visvoai
```

A full-terminal coding agent (Textual TUI) built for people who care about what
an agent is allowed to do:

- **A real permission model** — mutating actions ask first; read-only shell
  commands are classified and run inside an OS no-write sandbox
  (macOS `sandbox-exec` / Linux `bwrap`), so a disguised write fails at the
  kernel, not at a prompt.
- **Agents & subagents** — delegate work to built-in or user-defined agents
  (markdown files), dispatched in parallel, each an isolated conversation with
  live logs (`/runs`, side panel) and a persistent JSONL trace.
- **Skills** — teach it your workflows once (`SKILL.md` files, progressive
  disclosure); point it at skill libraries you already have
  (`~/.claude/skills`, a repo's `skills/`).
- **MCP** — connect Model Context Protocol servers with one config block;
  persistent sessions, so stateful servers (a browser, a DB) keep state.
- **Time-travel** — every turn is checkpointed; rewind files + conversation
  together, branch timelines, fork checkpoints into new folders.
- **Trust boundaries throughout** — anything a *repo* defines (project agents,
  skills, MCP servers) needs your one-time approval; anything *you* define is
  yours. Definitions are hashed; edits re-prompt.
- **Plugin tools** — drop a Python file in `~/.visvoai/tools/`, get
  model-callable tools with schemas from your type hints.

## The runtime under it

If you're building your *own* agent product — a support bot, an internal ops
agent, a domain CLI — `visvoai-core` is the ~1k lines everyone ends up writing
on top of LangGraph, already hardened by two real consumers (this CLI and a
hosted multi-tenant platform):

- the agent↔tools loop with a **soft step cap** that forces one clean final
  answer instead of dying at a recursion limit
- a **tool lifecycle** (`BaseAgentTool`): declare config, write `_execute()`,
  get registration, validation, and persistence hooks for free
- **semantic tool retrieval** — bind only relevant tools per round when you
  have too many to bind at all
- extension by **subclass + inject**, not forks: `AgentRuntime` hooks for extra
  graph nodes/checkpointers/interrupts, `RuntimeContext` for your state,
  `ToolPersistence` for your datastore

| Package | Use it when | Install |
|---------|-------------|---------|
| **[visvoai-cli](./visvoai-cli)** | you want the finished coding agent | `pip install visvoai-cli` |
| **[visvoai-core](./visvoai-core)** | you're building your own agent on LangGraph and want the loop, lifecycle, and seams solved | `pip install visvoai-core` |
| **[visvoai-ai](./visvoai-ai)** | you want one interface + a curated live model registry (thinking levels, cost, capabilities) across providers | `pip install "visvoai-ai[gemini]"` |

Honest positioning: `visvoai-core` is not a framework and doesn't want to be —
it's a thin, opinionated layer whose extension seams are proven by the two
products that run on them. If you need a hundred integrations, use LangChain
directly; if you need the loop done right, start here.

## Quick start (runtime)

```python
from visvoai.ai import build_chat_model
from visvoai.core.runtime import AgentRuntime

model = build_chat_model("gemini:gemini-2.5-flash")
graph = AgentRuntime().build_graph(
    model=model,
    core_tools=my_tools,                      # BaseTool / BaseAgentTool
    all_tools_map={t.name: t for t in my_tools},
    system_prompt="You are ...",
)
# graph is a LangGraph app: .ainvoke / .astream_events as usual
```

See [visvoai-core/README.md](./visvoai-core/README.md) for the extension seams
and [visvoai-ai/README.md](./visvoai-ai/README.md) for providers and the model
catalog.

## License

MIT — all three packages.
