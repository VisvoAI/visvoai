"""
Provider — the base facade interface (one subclass per provider family).

A single class per provider exposes what's needed for the LangGraph agent loop:

  • build_chat_model()     → return a streaming BaseChatModel for LangGraph
  • normalize_content()    → map streamed chunks to {type, content} events

Native one-shot generate/search/embed calls are intentionally out of scope for
this facade — a consumer that needs them adds its own methods on a subclass.

Rules:
  - All methods OPTIONAL (default NotSupported) — a provider implements only what it has.
  - LangChain isolated to build_chat_model/normalize_content (lazy import in subclasses).
  - Provider-neutral — never typed to a vendor SDK input.
"""
from abc import ABC
from typing import Any, Dict, Generator, Optional

from langchain_core.language_models import BaseChatModel


class NotSupported(NotImplementedError):
    """Raised when a provider doesn't support a given Provider capability."""


def default_content_events(chunk: Any) -> Generator[Dict[str, Any], None, None]:
    """The langchain-core list-of-blocks content shape (Gemini + Anthropic). Shared by the
    base Provider.normalize_content and used as TokenNormalizer's fallback. Yields {type, content}."""
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt == "thinking":
                text = block.get("thinking") or block.get("thinking_delta") or ""
                if text:
                    yield {"type": "thinking", "content": text}
            elif bt == "text":
                text = block.get("text") or block.get("text_delta") or ""
                if text:
                    yield {"type": "text", "content": text}
            elif bt == "redacted_thinking":
                yield {"type": "thinking_redacted", "content": ""}
            elif bt == "compaction":
                yield {"type": "compaction", "content": ""}
    elif isinstance(content, str) and content:
        yield {"type": "text", "content": content}


class Provider(ABC):
    """One provider family's full LLM surface for the agent loop.
    All methods optional (default NotSupported); a provider implements only what it supports."""

    def build_chat_model(self, *, model_id: str, api_key: Optional[str] = None,
                         base_url: Optional[str] = None, option=None,
                         thinking_level: Optional[str] = None) -> BaseChatModel:
        """Return a configured, streaming BaseChatModel for the LangGraph loop.

        api_key: explicit key; falls back to env var if omitted.
        base_url: for OpenAI-compatible endpoints; ignored by Gemini/Anthropic.
        """
        raise NotSupported(f"{type(self).__name__} cannot build a LangChain chat model")

    def normalize_content(self, chunk: Any) -> Generator[Dict[str, Any], None, None]:
        """Map a streamed chunk's CONTENT/THINKING to events {type, content}. Default =
        langchain-core list-of-blocks shape (Gemini + Anthropic); OpenAI-compat overrides."""
        yield from default_content_events(chunk)
