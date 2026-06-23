# visvoai-ai

Unified multi-provider LLM access layer. Abstracts Gemini, Anthropic, OpenAI,
and Together behind a single `Provider` facade and `ModelRegistry`.

# Key Files (once populated from backend/llm/)
- `src/visvoai/ai/__init__.py` → public API surface
- `src/visvoai/ai/providers/` → per-provider implementations of the Provider ABC
- `src/visvoai/ai/model_registry.py` → ModelDefinition + Capability enum + registry
- `src/visvoai/ai/base.py` → BaseLLMEngine ABC

# Key Classes / Functions (migration targets from backend/llm/)
- `Provider` → ABC with optional capability methods (from backend/llm/providers/base.py)
- `ModelDefinition` → dataclass with id, display_name, capabilities, provider (from backend/llm/model_registry.py)
- `Capability` → enum: TEXT, VISION, TOOL_USE, THINKING, SEARCH, etc.
- `ModelRegistry` → maps model IDs to providers; lookup by capability

# Conventions
- No platform dependencies (no DB, no auth, no sandbox references)
- All provider implementations are lazy-importable — google.genai import only when GeminiEngine is used
- `providers/config.py` owns key + base_url resolution: `resolve_api_key(provider, key)` and `resolve_base_url(provider, base_url)`. Explicit args always win; otherwise env var / `_PROVIDER_BASE_URL` default. Platform surfaces pass both explicitly from their own config.
- `AnthropicProvider.build_chat_model` reads `supports_thinking` from `model_registry` (single source of truth) — never hardcode model-id checks in the provider.

# Gotchas
- Together/Groq/OpenRouter run on the **OpenAI-compat path** (`OpenAICompatProvider` → `ChatOpenAI` + base_url), NOT a vendor SDK. No extra `pip install` needed — only an API key and base_url (auto-resolved in `config.py`).
- `OpenAICompatProvider.build_chat_model` raises `ValueError` if a non-`openai` provider has no resolvable base_url — prevents silent fall-through to OpenAI's API with a foreign model id.
- `ReasoningChatOpenAI` is a thin `__new__` shim over a memoized `_reasoning_chat_openai_cls()` — do not re-add per-call class creation.
