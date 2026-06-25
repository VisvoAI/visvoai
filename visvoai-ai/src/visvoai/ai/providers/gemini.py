"""GeminiProvider — facade for Google Gemini.

Low-level build() for the LangGraph agent loop. Thinking kwargs are computed by the
top-level resolver (visvoai.ai.build_chat_model) and passed in via **extra — the
provider just constructs. Subclass to add anything beyond chat (generate/search).
"""
from .base import Provider
from .config import resolve_api_key


class GeminiProvider(Provider):
    def build(self, slug, api_key=None, base_url=None, **extra):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=slug,
            google_api_key=resolve_api_key("gemini", api_key),
            temperature=1.0,
            streaming=True,
            **extra,
        )
