"""
Provider — the base facade interface (one subclass per provider family).

A single class per provider exposes that provider's full LLM surface. Consumers resolve
the provider from the model's `provider` field (`get_provider`, see __init__) and call:

  • build_chat_model()     → the LangGraph agent loop (LangChain; lazy import in impls)
  • generate()             → utility calls (title/compaction/query); NATIVE, no LangChain
  • search() / embed()     → optional capabilities

All methods accept api_key and base_url explicitly. If api_key is omitted, providers
fall back to the environment variable for that provider (via resolve_api_key). Platform
surfaces resolve and pass the key before calling — they never rely on env-var fallback.

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
    """One provider family's full LLM surface. All methods optional (default NotSupported);
    a provider implements only what it supports."""

    # ── LangGraph agent loop (LangChain — lazy import inside impls) ──────────────
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

    # ── Utility calls (NATIVE, LangChain-independent) ───────────────────────────
    def generate(self, *, model_id: str, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, prompt,
                 system: Optional[str] = None, tools=None,
                 max_tokens: int = 1000, temperature: float = 0.0, **kwargs):
        """Uniform native LLM call for utility paths (title/compaction/query).
        Returns (result, LLMStats): result is text when no tools, else the first
        function-call object (.name/.args). Non-streaming. Raises NotSupported if the
        provider has no native engine.
        **kwargs: platform subclasses may accept additional params (e.g. owner_id)."""
        raise NotSupported(f"{type(self).__name__}.generate not implemented")

    # ── Optional capabilities ───────────────────────────────────────────────────
    def search(self, *, model_id: str, api_key: Optional[str] = None,
               base_url: Optional[str] = None, **kwargs):
        """Grounded web search → (SearchTrace, LLMStats). Not all providers support it."""
        raise NotSupported(f"{type(self).__name__} has no search capability")

    def embed(self, *, model_id: str, api_key: Optional[str] = None,
              base_url: Optional[str] = None, **kwargs):
        """Embeddings. Not all providers support it."""
        raise NotSupported(f"{type(self).__name__} has no embed capability")


def run_engine(engine, prompt, *, system, tools, max_tokens, temperature):
    """Shared native-engine call (Gemini/Anthropic both back generate() with a
    BaseLLMEngine engine). Returns (result, LLMStats) — result = first function-call when
    tools, else the full text."""
    if tools:
        (first_call, _text), stats = engine.execute_tool_call(
            prompt, tools, max_tokens=max_tokens, temperature=temperature, system_instructions=system,
        )
        return first_call, stats
    gen = engine.execute_llm_call(
        prompt, stream=False, max_tokens=max_tokens, temperature=temperature, system_instructions=system,
    )
    full, stats = "", None
    try:
        while True:
            chunk = next(gen)
            if isinstance(chunk, str):
                full += chunk
    except StopIteration as stop:
        if stop.value:
            ret_text, stats = stop.value
            full = ret_text or full
    return full, stats
