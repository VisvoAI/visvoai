"""
visvoai.ai — Unified multi-provider LLM access.

Provides a single Provider facade across Gemini, Anthropic, OpenAI, and Together.
ModelRegistry maps model IDs to capability-aware provider implementations.
"""
from visvoai.ai.model_registry import (
    ModelDefinition,
    ModelOption,
    Capability,
)
from visvoai.ai.providers.base import Provider, NotSupported, default_content_events

__all__ = [
    "ModelDefinition",
    "ModelOption",
    "Capability",
    "Provider",
    "NotSupported",
    "default_content_events",
]
