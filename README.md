<p align="center"><img src="./assets/logo.svg" alt="VisvoAI" width="280"></p>

# VisvoAI™

[![tests](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml/badge.svg)](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml) [![PyPI](https://img.shields.io/pypi/v/visvoai.svg)](https://pypi.org/project/visvoai/) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/VisvoAI/visvoai)

**A terminal coding agent with a trust model — and the Python runtime it's built on.**

`visvoai` is an AI assistant that lives in your terminal. It reads your
code, edits files, and runs commands — but it must *ask you* before it
changes anything, and the operating system itself blocks what you didn't
approve. The engine under it is published here too, so you can build your
own agent with the same pieces.

```
visvoai-cli          the product: a full-screen terminal coding agent
     │               agents · skills · MCP tool servers · sandboxed shell · time-travel
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

- **The OS enforces the rules, not the prompt.** Commands that only *read*
  run instantly — inside an operating-system sandbox that physically cannot
  write to your disk. Commands that *change* things ask you first. Even if
  the AI is tricked, the sandbox is not.
- **Nothing from a downloaded repo turns itself on.** Agents, skills, and
  tools that a repo defines stay off until you approve them once — and if
  the file changes later, you are asked again.
- **The engine is published, not hidden.** Every agent product needs the
  same core loop, and most teams rebuild it badly once. Ours is here, tested
  by two real products, for the next person building their own.

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
step cap (clean final answers, never a recursion error), semantic tool
retrieval for fleet-scale tool sets, a tool
lifecycle with pluggable persistence, and subclass-and-inject extension
seams proven by two shipping consumers — this CLI and a hosted platform.

```python
def word_count(text: str) -> int:
    """Count the words in a piece of text."""     # ← a tool. That's all.
    return len(text.split())

from visvoai.core.runtime import AgentRuntime
graph = AgentRuntime().build_graph(model=model, core_tools=[word_count],
                                   system_prompt="You are ...")
```

Tools are plain typed functions, lifecycle classes with persistence hooks,
existing LangChain tools, or MCP servers — mixed freely in one list.

Honest positioning: not a framework and doesn't want to be — if you need a
hundred integrations, use LangChain directly; if you need the loop done
right, start here. **[Seams, examples, when-not-to-use → visvoai-core/README](./visvoai-core/README.md)** · **[Build your own product → BUILD-YOUR-OWN](./visvoai-core/BUILD-YOUR-OWN.md)**

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

Start with the capstone: **[a whole product in 180 lines](./visvoai-core/examples/07_everything_together.py)**
— an ops assistant with tool retrieval, memory, and an audit trail, runnable
with **no API key**. Then each package's examples go one idea at a time:
[cli](./visvoai-cli/examples/) (agents, skills, plugin tools, MCP config) ·
[core](./visvoai-core/examples/) (20-line agent → tool styles → retrieval →
persistence → capstone → subagents; six keyless) · [ai](./visvoai-ai/examples/) (models, registry,
custom providers). Full docs: each package's README.

## Finding your way around

Every directory carries an `AGENTS.md` — a terse map of what the module does,
its key files, conventions, and gotchas. They're written for AI coding tools
(Claude Code, Cursor, …) and kept in sync with the code, which makes them the
fastest orientation for humans too. Start at any package's root `AGENTS.md`
and drill down.

## License

MIT — all three packages.

If VisvoAI ends up in something you build, ship, or write about, a mention —
a link, a star, a "built on VisvoAI" line — is warmly appreciated. Never
required (that's what MIT means), always noticed.

[Contributing](./CONTRIBUTING.md) · [Security](./SECURITY.md) · [Code of Conduct](./CODE_OF_CONDUCT.md)
