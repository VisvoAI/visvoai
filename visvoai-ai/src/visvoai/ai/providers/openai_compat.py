"""OpenAICompatProvider — any OpenAI-compatible provider (openai/together/groq/vllm/…).

Includes ReasoningChatOpenAI: Together/DeepSeek/GLM/Qwen stream chain-of-thought in
the Chat Completions `delta.reasoning` field, which langchain-openai drops. The subclass
captures it into additional_kwargs["reasoning"] so normalize_content can surface it as a
thinking event, uniform with Gemini/Claude.
"""
from .base import Provider


class ReasoningChatOpenAI:
    """ChatOpenAI subclass that preserves the non-standard `delta.reasoning` field."""

    def __new__(cls, **kwargs):
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

        return _ReasoningChatOpenAI(**kwargs)


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

    def build_chat_model(self, *, config, model_id, owner_id=None, option=None, thinking_level=None):
        base_url = config.get_base_url(self.provider_name)
        return ReasoningChatOpenAI(
            model=model_id,
            api_key=config.get_key(self.provider_name, owner_id=owner_id),
            base_url=base_url,
            temperature=1.0,
            streaming=True,
            stream_usage=True,
        )
