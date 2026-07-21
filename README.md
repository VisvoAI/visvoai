<p align="center"><img src="./assets/lockup-horizontal.svg" alt="Visvo AI" width="330"></p>

[![tests](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml/badge.svg)](https://github.com/VisvoAI/visvoai/actions/workflows/tests.yml) [![PyPI](https://img.shields.io/pypi/v/visvoai.svg)](https://pypi.org/project/visvoai/) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/VisvoAI/visvoai)

**Works with:** Gemini · Claude · GPT · Groq · Together AI · OpenRouter · any
OpenAI-compatible endpoint — one key of your choice to start.

**The Python toolkit for building AI agents — plus the coding agent built on
it, as proof it holds up.** *(VisvoAI™)*

Calling a provider's raw API is easy; turning that into a real *agent* —
one that calls tools, remembers a conversation, knows what it costs, and
doesn't loop forever — is a week of plumbing every team ends up rebuilding.
VisvoAI is that plumbing, published: a model layer that speaks to any
provider, an agent loop built on it, and — running on both, unmodified — a
full terminal coding agent that proves the toolkit survives real use.

```
visvoai-ai            the foundation: one interface, many providers
     ▲                registry · thinking levels · cost · live catalog
     │
visvoai-core           the agent loop, built on it: done right, once
     ▲                tool lifecycle · retrieval · extension seams
     │
visvoai-cli             the proof: a full product, running on both
                       agents · skills · MCP · sandboxed shell · time-travel
```

Start wherever your problem is: need a model, not an agent? `visvoai-ai`
alone. Building your own agent product? `visvoai-core` is the loop, and
`visvoai-cli`'s source is a working reference for how far it goes. Just
want a coding agent right now? `pip install visvoai`.

Dependencies point one way only. Nothing here depends on any private or hosted
infrastructure — these packages *are* the runtime under a commercial platform,
published as they're used.

## What this actually gets you today

Going from zero to a working, multi-provider agent — with a real trust
model, not a toy — takes minutes, not the week of SDK-reading and
plumbing that calling providers directly usually costs. That part is
solved, and you can watch it happen with **no API key**: see
[the capstone example](./visvoai-core/examples/07_everything_together.py).

Honestly: production hardening — retries across providers, cost caps,
shipped observability — is still yours to add today. It's the top of our
[roadmap](https://github.com/VisvoAI/visvoai/issues?q=is%3Aissue+is%3Aopen+label%3Aroadmap),
not a secret. We'd rather tell you what's next than let you find out the
hard way.

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

### 🔌 `visvoai-ai` — the foundation: one interface, many providers

One line to any provider's streaming model, plus what most facades skip: a
live registry of model *facts* (pricing, context, capabilities, normalized
thinking levels) so your app can choose and meter models, not just call them.

```python
from visvoai.ai import build_chat_model, cost_of, usage_from
model = build_chat_model("anthropic:claude-sonnet-4-5", level="high")
```

**[Providers, registry, metering → visvoai-ai/README](./visvoai-ai/README.md)**

### ⚙️ `visvoai-core` — the agent loop, built on it

For building your *own* agent product: the loop with a soft
step cap (clean final answers, never a recursion error), semantic tool
retrieval for fleet-scale tool sets, a tool
lifecycle with pluggable persistence, and subclass-and-inject extension
seams proven by two shipping consumers — the CLI below and a hosted platform.

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

### 🖥 `visvoai-cli` — the proof: a full product, running on both

![visvoai — a real turn: read, edit, self-correct, verify, with live cost](./visvoai-cli/docs/hero.gif)

```bash
pip install visvoai        # or: pip install visvoai-cli
export GEMINI_API_KEY=...  # or Anthropic / OpenAI / any compatible
visvoai
```

Not a demo of the toolkit — the same `visvoai-core` loop and `visvoai-ai`
model layer, unmodified, under a full-terminal agent where the permission
model is enforced by the OS, not the prompt: kernel-sandboxed shell reads,
approval-gated writes, one-time trust for anything a repo defines, parallel
subagents with live logs, teachable skills, and time-travel across files +
conversation together. **[Full tour → visvoai-cli/README](./visvoai-cli/README.md)**

## Examples

Start with the capstone: **[a whole product in 180 lines](./visvoai-core/examples/07_everything_together.py)**
— an ops assistant with tool retrieval, memory, and an audit trail, runnable
with **no API key**. Then each package's examples go one idea at a time:
[ai](./visvoai-ai/examples/) (models, registry, custom providers) ·
[core](./visvoai-core/examples/) (20-line agent → tool styles → retrieval →
persistence → capstone → subagents; six keyless) ·
[cli](./visvoai-cli/examples/) (agents, skills, plugin tools, MCP config —
how the reference product is configured). Full docs: each package's README.

## Finding your way around

Every directory carries an `AGENTS.md` — a terse map of what the module does,
its key files, conventions, and gotchas. They're written for AI coding tools
(Claude Code, Cursor, …) and kept in sync with the code, which makes them the
fastest orientation for humans too. Start at any package's root `AGENTS.md`
and drill down.

## License

MIT — all three packages. (Code only: the VisvoAI name and logo are
[trademarks](./TRADEMARKS.md), not part of the license grant.)

If VisvoAI ends up in something you build, ship, or write about, a mention —
a link, a star, a "built on VisvoAI" line — is warmly appreciated. Never
required (that's what MIT means), always noticed.

[Contributing](./CONTRIBUTING.md) · [Security](./SECURITY.md) · [Code of Conduct](./CODE_OF_CONDUCT.md) · [Trademarks](./TRADEMARKS.md)

<sub>agentic AI · AI coding agent · terminal AI assistant · LLM agent
framework · LangGraph runtime · MCP client · multi-agent orchestration ·
sandboxed code execution · human-in-the-loop approvals</sub>
