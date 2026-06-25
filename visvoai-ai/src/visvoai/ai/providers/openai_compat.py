"""OpenAICompatProvider — any OpenAI-compatible provider (openai/together/groq/vllm/…).

Includes ReasoningChatOpenAI: Together/DeepSeek/GLM/Qwen stream chain-of-thought in
the Chat Completions `delta.reasoning` field, which langchain-openai drops. The subclass
captures it into additional_kwargs["reasoning"] so normalize_content can surface it as a
thinking event, uniform with Gemini/Claude.
"""
from .base import Provider
from .config import resolve_api_key, resolve_base_url

_REASONING_CLS = None


def _reasoning_chat_openai_cls():
    """Build (once) the ChatOpenAI subclass that preserves `delta.reasoning`.

    Memoized: the subclass is identical regardless of provider, so minting it per
    call would create a fresh Python type on every Together/DeepSeek/GLM/Qwen build.
    """
    global _REASONING_CLS
    if _REASONING_CLS is None:
        from langchain_openai import ChatOpenAI

        class _ReasoningChatOpenAI(ChatOpenAI):
            def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
                gen = super()._convert_chunk_to_generation_chunk(
                    chunk, default_chunk_class, base_generation_info
                )
                try:
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    reasoning = delta.get("reasoning")
                    if reasoning and gen is not None and gen.message is not None:
                        gen.message.additional_kwargs["reasoning"] = reasoning
                except Exception:
                    pass
                return gen

        _REASONING_CLS = _ReasoningChatOpenAI
    return _REASONING_CLS


class ReasoningChatOpenAI:
    """ChatOpenAI subclass that preserves the non-standard `delta.reasoning` field."""

    def __new__(cls, **kwargs):
        return _reasoning_chat_openai_cls()(**kwargs)


class OpenAICompatProvider(Provider):
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def normalize_content(self, chunk):
        content = getattr(chunk, "content", None)
        if isinstance(content, str) and content:
            yield {"type": "text", "content": content}
        reasoning = (getattr(chunk, "additional_kwargs", None) or {}).get("reasoning")
        if reasoning:
            yield {"type": "thinking", "content": reasoning}

    def build(self, slug, api_key=None, base_url=None, **extra):
        resolved_base_url = resolve_base_url(self.provider_name, base_url)
        # OpenAI itself runs on the library default (None). Any other compat
        # provider without a resolvable base_url would silently hit OpenAI's API
        # with a foreign model id — fail loudly instead.
        if self.provider_name.lower() != "openai" and not resolved_base_url:
            raise ValueError(
                f"OpenAICompatProvider('{self.provider_name}') has no base_url. "
                f"Pass base_url= explicitly when building the chat model. "
                f"(Packages that ship a built-in default for this provider register "
                f"it in visvoai.ai.providers.config; third-party callers should just "
                f"pass base_url=.)"
            )
        return ReasoningChatOpenAI(
            model=slug,
            api_key=resolve_api_key(self.provider_name, api_key),
            base_url=resolved_base_url,
            temperature=1.0,
            streaming=True,
            stream_usage=True,
            **extra,
        )
