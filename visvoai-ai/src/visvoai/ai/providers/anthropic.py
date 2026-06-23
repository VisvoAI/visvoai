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
        from visvoai.ai.model_registry import get_model
        # Single source of truth: the registry decides which models accept the
        # extended-thinking parameter. Unknown ids default to off (safe).
        _md = get_model(model_id)
        supports_thinking = _md.supports_thinking if _md else False
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
