"""
visvoai.ai.providers.config — API key resolution for public providers.

resolve_api_key(provider, api_key) is the single entry point:
  1. Use api_key if explicitly passed.
  2. Fall back to the environment variable for that provider.
  3. Raise KeyError with a clear message if neither is set.

Providers call this internally from build_chat_model(): pass api_key= to
override, otherwise the matching environment variable is used.
"""
from __future__ import annotations

import os
from typing import Optional

_ENV_KEY_MAP = {
    "gemini":    "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "together":  "TOGETHER_API_KEY",
    "groq":      "GROQ_API_KEY",
}

# OpenAI-compatible providers reached via ChatOpenAI + base_url. "openai" itself
# is absent: it uses the library default (None). An explicit base_url passed by
# the caller always overrides these built-in defaults.
_PROVIDER_BASE_URL = {
    "together":   "https://api.together.xyz/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def resolve_base_url(provider: str, base_url: Optional[str] = None) -> Optional[str]:
    """Return the base_url for an OpenAI-compatible provider.

    Priority: explicit base_url arg → per-provider default → None (OpenAI itself).
    """
    if base_url:
        return base_url
    return _PROVIDER_BASE_URL.get(provider.lower())


def resolve_api_key(provider: str, api_key: Optional[str] = None) -> str:
    """Return the API key for provider.

    Priority: explicit api_key arg → environment variable → KeyError.
    """
    if api_key:
        return api_key
    env_var = _ENV_KEY_MAP.get(provider.lower())
    if env_var:
        key = os.environ.get(env_var, "")
        if key:
            return key
    raise KeyError(
        f"No API key found for provider '{provider}'. "
        f"Pass api_key= explicitly or set the "
        f"{_ENV_KEY_MAP.get(provider.lower(), provider.upper() + '_API_KEY')} "
        f"environment variable."
    )
