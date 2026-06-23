# visvoai-ai

Unified, multi-provider LLM access for Python — one small facade per provider
family, plus a single source of truth for model identity, pricing, and
capabilities.

`visvoai-ai` has no dependency on any agent framework, datastore, or web layer.
It gives you a streaming `BaseChatModel` (LangChain-compatible) for the provider
you want, and gets out of the way.

## Install

The base install is light. Pull only the provider integration you use:

```bash
pip install "visvoai-ai[gemini]"      # Google Gemini
pip install "visvoai-ai[anthropic]"   # Anthropic Claude
pip install "visvoai-ai[openai]"      # OpenAI + any OpenAI-compatible endpoint
pip install "visvoai-ai[all]"         # all of the above
```

OpenAI-compatible providers (Together, Groq, OpenRouter, vLLM, …) run on the
`[openai]` extra — they only need an API key and a `base_url`.

## Usage

```python
from visvoai.ai.providers.gemini import GeminiProvider

provider = GeminiProvider()
model = provider.build_chat_model(model_id="gemini-2.5-flash")  # a streaming BaseChatModel

for chunk in model.stream("Explain attention in one sentence."):
    print(chunk.content, end="")
```

API keys resolve from the matching environment variable (`GEMINI_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …) unless you pass `api_key=` explicitly.

## Extending

`Provider` is a base facade. Subclass it to add a new provider family, or to add
methods beyond chat (e.g. one-shot generate/search) — only `build_chat_model()`
and `normalize_content()` are part of the core interface, and both are optional.

## License

MIT
