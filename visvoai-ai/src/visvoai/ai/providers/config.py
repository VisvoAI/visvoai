"""
visvoai.ai.providers.config — API key resolution for the public package.

Public providers read keys from environment variables. Platform surfaces
inject a concrete ApiKeyConfig subclass that reads from the DB/vault instead.

Usage (public — env vars):
    config = ApiKeyConfig()
    key = config.get_key("gemini")

Usage (platform — override):
    class PlatformConfig(ApiKeyConfig):
        def get_key(self, provider: str, *, owner_id: str | None = None) -> str:
            return self._vault.get(provider, owner_id)
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


class ApiKeyConfig:
    """Resolve provider API keys. Default: reads from environment variables.

    Platform subclasses override get_key() to read from a secrets store instead.
    """

    def get_key(self, provider: str, *, owner_id: Optional[str] = None) -> str:
        """Return the API key for provider. Raises KeyError if not found."""
        env_var = _ENV_KEY_MAP.get(provider.lower())
        if env_var:
            key = os.environ.get(env_var, "")
            if key:
                return key
        raise KeyError(
            f"No API key found for provider '{provider}'. "
            f"Set the {_ENV_KEY_MAP.get(provider.lower(), provider.upper() + '_API_KEY')} "
            f"environment variable."
        )

    def get_base_url(self, provider: str) -> Optional[str]:
        """Return the base URL for an OpenAI-compatible provider. Default: None (use SDK default)."""
        return None
