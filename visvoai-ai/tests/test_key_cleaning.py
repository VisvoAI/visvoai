"""resolve_api_key cleans whitespace + wrapping quotes (the silent-401 fix)."""
import pytest

from visvoai.ai.providers.config import _clean_key, resolve_api_key


def test_clean_strips_whitespace_and_quotes():
    assert _clean_key("  sk-abc \n") == "sk-abc"
    assert _clean_key('"sk-abc"') == "sk-abc"
    assert _clean_key("'sk-abc'") == "sk-abc"
    assert _clean_key('"sk-abc" ') == "sk-abc"
    assert _clean_key(None) == ""
    assert _clean_key("   ") == ""


def test_resolve_cleans_explicit_key():
    assert resolve_api_key("openai", api_key="  sk-x \n") == "sk-x"


def test_resolve_cleans_env_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", '"sk-env "')   # wrapped + trailing space
    assert resolve_api_key("openai") == "sk-env"


def test_resolve_raises_when_only_whitespace(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")          # blank after strip → not found
    with pytest.raises(KeyError):
        resolve_api_key("openai")
