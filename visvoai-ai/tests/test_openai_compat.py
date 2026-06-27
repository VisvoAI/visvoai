"""OpenAICompatProvider pins Chat Completions for non-OpenAI providers — the
Responses API is OpenAI-proprietary and compat providers (Together/OpenRouter/…)
reject it or corrupt the next turn with block-list content."""
import pytest

from visvoai.ai.providers.openai_compat import OpenAICompatProvider

pytest.importorskip("langchain_openai")  # build() needs ChatOpenAI; an optional extra


def test_non_openai_provider_pins_chat_completions():
    m = OpenAICompatProvider("together").build(
        "MiniMaxAI/MiniMax-M3", base_url="https://api.together.xyz/v1", api_key="x")
    assert m.use_responses_api is False


def test_explicit_override_respected():
    m = OpenAICompatProvider("together").build(
        "x", base_url="https://api.together.xyz/v1", api_key="x", use_responses_api=True)
    assert m.use_responses_api is True


def test_openai_left_to_library_default():
    m = OpenAICompatProvider("openai").build("gpt-4o-mini", api_key="x")
    assert m.use_responses_api is None   # langchain decides (reasoning models → /responses)
