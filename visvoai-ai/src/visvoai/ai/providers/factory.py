"""
visvoai.ai.providers.factory — resolve a provider name (or model id) to a Provider facade.

Two entry points, both key-less — they pick the right facade CLASS; they do not
resolve API keys (each Provider resolves its own key from the env or an explicit
api_key= at build_chat_model time). A consumer that keys providers from its own
config layer wraps these and passes api_key= through.

  get_provider(name)            name → facade. Bespoke-SDK families (gemini,
                                anthropic) have dedicated facades; every other
                                name (together, openai, groq, openrouter, …) is
                                OpenAI-API-compatible.
  get_provider_for_model(id)    registry-driven: model id → its declared
                                provider → facade. Raises on an unregistered id.
"""
from __future__ import annotations

from typing import Optional

from visvoai.ai.model_registry import Capability, get_model
from visvoai.ai.providers.anthropic import AnthropicProvider
from visvoai.ai.providers.base import Provider
from visvoai.ai.providers.gemini import GeminiProvider
from visvoai.ai.providers.openai_compat import OpenAICompatProvider

# Families with a bespoke (non-OpenAI-shaped) client. Everything else → OpenAI-compat facade.
_SPECIFIC = {
    "gemini": GeminiProvider(),
    "anthropic": AnthropicProvider(),
}


def get_provider(provider_name: Optional[str]) -> Provider:
    """Resolve the Provider facade for a provider name (a ModelDefinition.provider value).

    Bespoke-SDK families (gemini, anthropic) have dedicated facades; every other
    name (together, openai, groq, openrouter, …) is OpenAI-API-compatible.
    Raises ValueError on empty/None.
    """
    if not provider_name:
        raise ValueError("get_provider requires a provider name (got None/empty)")
    if provider_name in _SPECIFIC:
        return _SPECIFIC[provider_name]
    return OpenAICompatProvider(provider_name)


def get_provider_for_model(model_id: str, capability: Optional[Capability] = None) -> Provider:
    """Resolve a model id → its Provider facade via the registry.

    Registry-driven: the model MUST be registered. Raises ValueError on an
    unregistered id, or — when capability is given — if the model does not
    declare that capability.
    """
    md = get_model(model_id)
    if md is None:
        raise ValueError(
            f"Unknown model id '{model_id}': not in the model registry. "
            f"Register it before use."
        )
    if capability is not None and capability not in md.capabilities:
        raise ValueError(
            f"Model '{model_id}' does not declare capability '{capability.value}' "
            f"(has {[c.value for c in md.capabilities]})."
        )
    return get_provider(md.provider)
