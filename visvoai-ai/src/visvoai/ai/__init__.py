"""
visvoai.ai — Unified multi-provider LLM access.

Provides a single Provider facade across Gemini, Anthropic, OpenAI, and Together.
ModelRegistry maps model IDs to capability-aware provider implementations.

Quick start:
    from visvoai.ai import GeminiProvider, ApiKeyConfig
    config = ApiKeyConfig()  # reads GEMINI_API_KEY from env
    model = GeminiProvider().build_chat_model(config=config, model_id="gemini-2.5-flash")
"""
from visvoai.ai.model_registry import (
    ModelDefinition,
    ModelOption,
    Capability,
)
from visvoai.ai.providers.base import Provider, NotSupported, default_content_events
from visvoai.ai.providers.config import ApiKeyConfig
from visvoai.ai.providers.gemini import GeminiProvider
from visvoai.ai.providers.anthropic import AnthropicProvider
from visvoai.ai.providers.openai_compat import OpenAICompatProvider, ReasoningChatOpenAI

__all__ = [
    "ModelDefinition",
    "ModelOption",
    "Capability",
    "Provider",
    "NotSupported",
    "default_content_events",
    "ApiKeyConfig",
    "GeminiProvider",
    "AnthropicProvider",
    "OpenAICompatProvider",
    "ReasoningChatOpenAI",
]
