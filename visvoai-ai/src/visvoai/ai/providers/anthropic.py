"""AnthropicProvider — facade for Anthropic Claude.

Public interface: build_chat_model() for the LangGraph agent loop.
Platform surfaces extend this with generate() via engine delegation.
"""
from .base import Provider


class AnthropicProvider(Provider):
    def build_chat_model(self, *, config, model_id, owner_id=None, option=None, thinking_level=None):
        from langchain_anthropic import ChatAnthropic
        # Older Claude models (3.x) don't support the extended thinking API.
        supports_thinking = not any(
            s in model_id
            for s in ("claude-3-5", "claude-3-opus", "claude-3-haiku", "claude-3-sonnet")
        )
        kwargs = dict(
            model=model_id,
            anthropic_api_key=config.get_key("anthropic", owner_id=owner_id),
            temperature=1.0,
            max_tokens=16000,
            streaming=True,
        )
        if supports_thinking and option and getattr(option, "thinking_budget", None) is not None:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": option.thinking_budget}
        return ChatAnthropic(**kwargs)
