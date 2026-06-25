"""AnthropicProvider — facade for Anthropic Claude.

Low-level build() for the LangGraph agent loop. Thinking kwargs (the extended-
thinking `thinking={...}` block) are computed by the top-level resolver and passed
in via **extra — the provider just constructs. Subclass to add one-shot generate.
"""
from .base import Provider
from .config import resolve_api_key


class AnthropicProvider(Provider):
    def build(self, slug, api_key=None, base_url=None, **extra):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=slug,
            anthropic_api_key=resolve_api_key("anthropic", api_key),
            temperature=1.0,
            max_tokens=16000,
            streaming=True,
            **extra,
        )
