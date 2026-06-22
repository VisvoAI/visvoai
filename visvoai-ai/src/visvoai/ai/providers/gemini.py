"""GeminiProvider — facade for Google Gemini.

Public interface: build_chat_model() for the LangGraph agent loop.
Platform surfaces extend this with generate() and search() via engine delegation.
"""
from .base import Provider, NotSupported
from visvoai.ai.model_registry import resolve_gemini_thinking_kwargs


class GeminiProvider(Provider):
    def build_chat_model(self, *, config, model_id, owner_id=None, option=None, thinking_level=None):
        from langchain_google_genai import ChatGoogleGenerativeAI
        thinking_kwargs = resolve_gemini_thinking_kwargs(model_id, thinking_level)
        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=config.get_key("gemini", owner_id=owner_id),
            temperature=1.0,
            streaming=True,
            **thinking_kwargs,
        )
