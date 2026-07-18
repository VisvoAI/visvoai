<p align="center"><img src="./assets/logo.svg" alt="VisvoAI" width="280"></p>

# VisvoAI™

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

## Why this exists

Coding agents are the most capable tools ever handed a shell — and most run
on politeness: a prompt that says "please ask before deleting things." We
think the boundaries should be real. That conviction, applied three times:

- **An agent's permissions should be enforced by the OS, not the prompt** —
  so the CLI classifies shell commands and runs reads inside a kernel
  no-write sandbox; a disguised write *fails*, not "should have asked."
- **Anything a repo defines must not silently arm itself** — so agents,
  skills, and MCP servers a repo ships need your one-time, hash-pinned
  approval.
- **The loop under an agent product is always the same ~1k lines, and
  everyone writes them badly once** — so the runtime beneath this CLI (and a
  hosted platform) is published for the next person building their own.

## What's in this repo

Three packages, one conviction each — use any layer on its own.

### 🖥 `visvoai-cli` — the coding agent

![visvoai — a real turn: read, edit, self-correct, verify, with live cost](./visvoai-cli/docs/hero.gif)

```bash
pip install visvoai        # or: pip install visvoai-cli
export GEMINI_API_KEY=...  # or Anthropic / OpenAI / any compatible
visvoai
```

A full-terminal agent where the permission model is enforced by the OS, not
the prompt: kernel-sandboxed shell reads, approval-gated writes, one-time
trust for anything a repo defines (agents, skills, MCP servers), parallel
subagents with live logs, teachable skills, and time-travel across files +
conversation together. **[Full tour → visvoai-cli/README](./visvoai-cli/README.md)**

### ⚙️ `visvoai-core` — the agent runtime

For building your *own* agent product on LangGraph: the loop with a soft
step cap (clean final answers, never a recursion error), duplicate-call
blocking, semantic tool retrieval for fleet-scale tool sets, a tool
lifecycle with pluggable persistence, and subclass-and-inject extension
seams proven by two shipping consumers — this CLI and a hosted platform.

```python
from visvoai.core.runtime import AgentRuntime
graph = AgentRuntime().build_graph(model=model, core_tools=tools,
                                   all_tools_map={t.name: t for t in tools},
                                   system_prompt="You are ...")
```

Honest positioning: not a framework and doesn't want to be — if you need a
hundred integrations, use LangChain directly; if you need the loop done
right, start here. **[Seams, examples, when-not-to-use → visvoai-core/README](./visvoai-core/README.md)**

### 🔌 `visvoai-ai` — the model layer

One line to any provider's streaming model, plus what most facades skip: a
live registry of model *facts* (pricing, context, capabilities, normalized
thinking levels) so your app can choose and meter models, not just call them.

```python
from visvoai.ai import build_chat_model, cost_of, usage_from
model = build_chat_model("anthropic:claude-sonnet-4-5", level="high")
```

**[Providers, registry, metering → visvoai-ai/README](./visvoai-ai/README.md)**

## Examples

Every package ships runnable, live-verified examples:
[cli](./visvoai-cli/examples/) (agents, skills, plugin tools, MCP config) ·
[core](./visvoai-core/examples/) (20-line agent → tool styles → retrieval →
persistence; three keyless) · [ai](./visvoai-ai/examples/) (models, registry,
custom providers). Full docs: each package's README.

## Finding your way around

Every directory carries an `AGENTS.md` — a terse map of what the module does,
its key files, conventions, and gotchas. They're written for AI coding tools
(Claude Code, Cursor, …) and kept in sync with the code, which makes them the
fastest orientation for humans too. Start at any package's root `AGENTS.md`
and drill down.

## License

MIT — all three packages.
