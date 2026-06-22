"""
visvoai.ai — Unified multi-provider LLM access.

Provides a single Provider facade across Gemini, Anthropic, OpenAI, and Together.
ModelRegistry maps model IDs to capability-aware provider implementations.

Quick start:
    from visvoai.ai import GeminiProvider
    model = GeminiProvider().build_chat_model(model_id="gemini-2.5-flash")
    # GEMINI_API_KEY env var used automatically — pass api_key= to override
"""
from visvoai.ai.model_registry import (
    ModelDefinition,
    Capability,
    get_model,
    resolve_gemini_thinking_kwargs,
)
from visvoai.ai.providers.base import Provider, NotSupported, default_content_events
from visvoai.ai.providers.config import resolve_api_key
from visvoai.ai.providers.gemini import GeminiProvider
from visvoai.ai.providers.anthropic import AnthropicProvider
from visvoai.ai.providers.openai_compat import OpenAICompatProvider, ReasoningChatOpenAI

__all__ = [
    "ModelDefinition",
    "Capability",
    "get_model",
    "resolve_gemini_thinking_kwargs",
    "Provider",
    "NotSupported",
    "default_content_events",
    "resolve_api_key",
    "GeminiProvider",
    "AnthropicProvider",
    "OpenAICompatProvider",
    "ReasoningChatOpenAI",
]
