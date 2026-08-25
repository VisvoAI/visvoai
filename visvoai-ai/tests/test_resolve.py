"""Tests for the public resolver: deployment id → provider.build with right args."""
import pytest

import visvoai.ai.resolve as resolve
from visvoai.ai import build_chat_model, cost_of


class _Fake:
    """Records what build() was called with; returns a sentinel."""
    def __init__(self, sink):
        self._sink = sink

    def build(self, slug, api_key=None, base_url=None, **extra):
        self._sink.update(slug=slug, api_key=api_key, base_url=base_url, extra=extra)
        return ("MODEL", slug, extra)


@pytest.fixture
def captured(monkeypatch):
    sink = {}
    monkeypatch.setattr(resolve, "get_provider",
                        lambda name: (sink.update(provider=name) or _Fake(sink)))
    return sink


def test_resolves_provider_slug_and_thinking(captured):
    build_chat_model("gemini:gemini-3-flash-preview", level="high")
    assert captured["provider"] == "gemini"
    assert result == "gemini-3-flash-preview"


def test_ollama_resolve_api_key_keyless() -> None:
    """Ollama resolves to empty string when no key is set"""
    from visvoai.ai.providers.config import resolve_api_key
    key = resolve_api_key("ollama")
    assert key == ""


def test_ollama_default_base_url() -> None:
    """Ollama resolves to localhost base_url by default"""
    from visvoai.ai.providers.config import resolve_base_url
    url = resolve_base_url("ollama")
    assert url == "http://localhost:11434/v1"

    assert captured["extra"] == {"thinking_level": "high", "include_thoughts": True}


def test_effort_from_id_when_no_explicit_level(captured):
    build_chat_model("gemini:gemini-3-flash-preview@low")
    assert captured["extra"] == {"thinking_level": "low", "include_thoughts": True}


def test_explicit_level_overrides_id_effort(captured):
    build_chat_model("gemini:gemini-3-flash-preview@low", level="high")
    assert captured["extra"]["thinking_level"] == "high"


def test_falls_back_to_deployment_default(captured):
    # gemini-3-flash-preview defaults to "medium" (default_thinking_label "Think")
    build_chat_model("gemini:gemini-3-flash-preview")
    assert captured["extra"]["thinking_level"] == "medium"


def test_thinking_raw_passthrough(captured):
    build_chat_model("gemini:gemini-3-flash-preview", thinking_raw={"foo": 1})
    assert captured["extra"] == {"foo": 1}


def test_multi_provider_same_model_picks_right_slug(captured):
    build_chat_model("openrouter:llama-3.3-70b")
    assert captured["provider"] == "openrouter"
    assert captured["slug"] == "meta-llama/llama-3.3-70b-instruct"
    assert captured["extra"] == {}        # non-reasoning → no thinking kwargs


def test_unknown_deployment_raises(captured):
    with pytest.raises(ValueError):
        build_chat_model("nope:missing")


def test_cost_of():
    c = cost_of("gemini:gemini-3-flash-preview", 1_000_000, 1_000_000)
    # 0.50 in + 3.00 out per million
    assert round(c, 4) == 3.50
