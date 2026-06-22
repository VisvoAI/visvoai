"""AnthropicProvider — facade for Anthropic Claude.

Public interface: build_chat_model() for the LangGraph agent loop.
Platform surfaces extend this with generate() via engine delegation.
"""
from .base import Provider
from .config import resolve_api_key


class AnthropicProvider(Provider):
    def build_chat_model(self, *, model_id, api_key=None, base_url=None,
                         option=None, thinking_level=None):
        from langchain_anthropic import ChatAnthropic
        supports_thinking = not any(
            s in model_id
            for s in ("claude-3-5", "claude-3-opus", "claude-3-haiku", "claude-3-sonnet")
        )
        kwargs = dict(
            model=model_id,
            anthropic_api_key=resolve_api_key("anthropic", api_key),
            temperature=1.0,
            max_tokens=16000,
            streaming=True,
        )
        if supports_thinking and option and getattr(option, "thinking_budget", None) is not None:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": option.thinking_budget}
        return ChatAnthropic(**kwargs)
