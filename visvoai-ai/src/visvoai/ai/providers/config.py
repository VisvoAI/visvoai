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
    "gemini":     "GEMINI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "together":   "TOGETHER_API_KEY",
    "groq":       "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
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


def _clean_key(raw: Optional[str]) -> str:
    """Strip whitespace and a single layer of surrounding matching quotes from a key.

    Keys reach us from shells, .env files, and config — any of which can leave a
    trailing newline/space or wrap the value in quotes. Sending that verbatim is the
    classic silent 401 ('User not found'), so every key is cleaned at this one
    chokepoint before it goes to a provider."""
    if not raw:
        return ""
    k = raw.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in ("'", '"'):
        k = k[1:-1].strip()
    return k


def resolve_api_key(provider: str, api_key: Optional[str] = None,
                    env_var: Optional[str] = None) -> str:
    """Return the API key for provider, cleaned (whitespace + wrapping quotes stripped).

    Priority: explicit api_key arg → explicit env_var (carried from a catalog source,
    e.g. models.dev) → the static _ENV_KEY_MAP env var → KeyError. `env_var` lets a
    catalog-sourced provider that isn't in the static map name its own key variable.
    """
    cleaned = _clean_key(api_key)
    if cleaned:
        return cleaned
    for var in (env_var, _ENV_KEY_MAP.get(provider.lower())):
        if var:
            key = _clean_key(os.environ.get(var))
            if key:
                return key
    expected = env_var or _ENV_KEY_MAP.get(provider.lower()) or provider.upper() + "_API_KEY"
    raise KeyError(
        f"No API key found for provider '{provider}'. "
        f"Pass api_key= explicitly or set the {expected} environment variable."
    )
