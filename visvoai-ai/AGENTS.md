# visvoai-ai

Unified multi-provider LLM access layer. Abstracts Gemini, Anthropic, OpenAI, and
every OpenAI-compatible endpoint behind a single `Provider` facade, plus a model
registry that is the single source of truth for model identity, pricing, and
capabilities.

# Key Files
- `src/visvoai/ai/__init__.py` → public API surface (re-exports providers + registry helpers)
- `src/visvoai/ai/providers/base.py` → `Provider` facade ABC + `NotSupported` + `default_content_events`
- `src/visvoai/ai/providers/gemini.py` → `GeminiProvider`
- `src/visvoai/ai/providers/anthropic.py` → `AnthropicProvider`
- `src/visvoai/ai/providers/openai_compat.py` → `OpenAICompatProvider` + `ReasoningChatOpenAI`
- `src/visvoai/ai/providers/config.py` → API-key + base_url resolution
- `src/visvoai/ai/model_registry.py` → model facts (ids, pricing, capabilities) + helpers

# Key Classes / Functions
- `Provider` → base facade; `build_chat_model()` returns a streaming LangChain `BaseChatModel`, `normalize_content()` maps stream chunks to `{type, content}` events. Both optional (default `NotSupported`).
- `GeminiProvider` / `AnthropicProvider` / `OpenAICompatProvider` → one subclass per family; lazily import their LangChain integration inside `build_chat_model()`.
- `resolve_api_key(provider, key)` / `resolve_base_url(provider, base_url)` → explicit arg wins, else env var / built-in base_url default.

# Conventions
- No dependency on any agent framework, datastore, web, or auth layer — pure LLM access.
- Provider integrations import lazily — the LangChain wrapper loads only when that provider's `build_chat_model()` is called.
- LangChain integration packages are declared as **per-provider extras** (`visvoai-ai[gemini]`, `[anthropic]`, `[openai]`, `[all]`) — base install stays light.
- `AnthropicProvider.build_chat_model` reads `supports_thinking` from `model_registry` (single source of truth) — never hardcode model-id checks in the provider.
- Public docstrings describe only the generic facade — no private/consumer internals.

# Gotchas
- Together/Groq/OpenRouter/vLLM run on the **OpenAI-compat path** (`OpenAICompatProvider` → `ChatOpenAI` + base_url), not a vendor SDK — they ship under the `[openai]` extra; only an API key + base_url (auto-resolved in `config.py`) are needed.
- `OpenAICompatProvider.build_chat_model` raises `ValueError` if a non-`openai` provider has no resolvable base_url — prevents silent fall-through to OpenAI's API with a foreign model id.
- `ReasoningChatOpenAI` is a thin `__new__` shim over a memoized `_reasoning_chat_openai_cls()` — do not re-add per-call class creation.
