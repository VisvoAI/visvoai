"""
visvoai.ai.providers.config — API key resolution for public providers.

resolve_api_key(provider, api_key) is the single entry point:
  1. Use api_key if explicitly passed.
  2. Fall back to the environment variable for that provider.
  3. Raise KeyError with a clear message if neither is set.

Platform surfaces resolve keys before calling provider methods and pass them
directly as api_key= — they never call resolve_api_key themselves.
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
