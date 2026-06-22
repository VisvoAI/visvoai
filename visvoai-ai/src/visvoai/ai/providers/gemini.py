"""GeminiProvider — facade for Google Gemini.

Public interface: build_chat_model() for the LangGraph agent loop.
Platform surfaces extend this with generate() and search() via engine delegation.
"""
from .base import Provider
from .config import resolve_api_key
from visvoai.ai.model_registry import resolve_gemini_thinking_kwargs


class GeminiProvider(Provider):
    def build_chat_model(self, *, model_id, api_key=None, base_url=None,
                         option=None, thinking_level=None):
        from langchain_google_genai import ChatGoogleGenerativeAI
        thinking_kwargs = resolve_gemini_thinking_kwargs(model_id, thinking_level)
        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=resolve_api_key("gemini", api_key),
            temperature=1.0,
            streaming=True,
            **thinking_kwargs,
        )
