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

# Gotchas
- `backend/llm/base.py` has a bad top-level import of `InteractionInput` from google.genai — needs lazy-import fix before migration
- Together provider (Phase 1 shipped) wraps the Together Python SDK, not OpenAI-compatible endpoint
