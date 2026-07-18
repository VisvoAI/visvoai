# visvoai-ai

**One line to any model — with the model *facts* included.** *(VisvoAI™)*

Every provider has its own SDK, its own model names, its own pricing page,
and its own spelling of "reasoning" — and your app ends up hardcoding all of
it. `visvoai-ai` is the antidote: a streaming, LangChain-compatible chat
model for whichever provider you name, plus the thing most facades skip —
a live model registry that knows each model's pricing, context window,
capabilities, and reasoning ("thinking") levels, so your app can *choose* and
*meter* models, not just call them.

You say `"anthropic:claude-sonnet-4-5"`, you get a working model — and you
can ask it what it costs, how big its context is, and what it can do, before
you spend a cent. No agent framework, no datastore, no web layer. Build a
model, get out of the way.

## Install

Base install is light; pull only the provider you use:

```bash
pip install "visvoai-ai[gemini]"      # Google Gemini
pip install "visvoai-ai[anthropic]"   # Anthropic Claude
pip install "visvoai-ai[openai]"      # OpenAI + any OpenAI-compatible endpoint
pip install "visvoai-ai[all]"         # everything
```

OpenAI-compatible providers (Together, Groq, OpenRouter, vLLM, …) ride the
`[openai]` extra — an API key and a `base_url` is all they need.

## One line to a model

```python
from visvoai.ai import build_chat_model

model = build_chat_model("gemini:gemini-2.5-flash")          # a streaming BaseChatModel
model = build_chat_model("anthropic:claude-sonnet-4-5", level="high")   # with thinking

for chunk in model.stream("Explain attention in one sentence."):
    print(chunk.content, end="")
```

API keys resolve from the matching environment variable (`GEMINI_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …); pass `api_key=` to override.

## The registry: choose and meter, not just call

```python
from visvoai.ai import list_deployments, Capability, cost_of, usage_from

for d in list_deployments(Capability.CHAT):
    print(d.id, d.display_name, d.input_cost_per_million, d.context_window,
          d.supports_thinking, [l.value for l in d.thinking_levels])

# after a call:
u = usage_from(response)                       # {'input': …, 'output': …, 'total': …}
usd = cost_of("gemini:gemini-2.5-flash", u["input"], u["output"])
```

The catalog is a curated baked set **plus** the
[models.dev](https://models.dev) catalog for providers you have keys for — so
new models appear without a package upgrade, and a keyless install still shows
a sane curated list.

## Thinking levels, normalized

Every provider spells reasoning differently (budgets, effort strings, on/off).
`visvoai-ai` normalizes them to one scale — `off · low · medium · high` — and
translates per provider, with each model's *supported* levels declared in the
registry. `build_chat_model(id, level="medium")` does the right thing
everywhere.

## Also in the box

- `run_search(...)` / `fetch_url(...)` — provider-grounded web search and URL
  fetch behind one seam (used by agent tools; no SDK leakage into your code).
- `Provider` base class — add a provider family by subclassing; only
  `build_chat_model()` and `normalize_content()` are core, both optional.
- Deterministic deployment identity (`provider:model` codec) — stable ids you
  can store, route on, and bill against.

## Who uses it

[`visvoai-core`](https://pypi.org/project/visvoai-core/) (agent runtime) and
[`visvoai-cli`](https://pypi.org/project/visvoai-cli/) (a terminal coding
agent whose model picker is this registry, live) — plus a hosted platform on
the same seam. If you only need "call one model I already chose," a raw SDK is
fine; this earns its keep the moment you support *choice* — multiple
providers, visible costs, or reasoning controls.

## Examples

Runnable, live-verified examples in [`examples/`](./examples/) — one-line
model access, registry choose-and-meter (keyless), OpenAI-compatible
endpoints and custom providers.

## License

MIT
