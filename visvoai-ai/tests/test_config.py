"""Tests for API-key resolution: explicit arg > env var > KeyError."""
import pytest

from visvoai.ai.providers.config import resolve_api_key, resolve_base_url


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every provider key the test cares about, so the test is deterministic."""
    for var in [
        "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "TOGETHER_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_explicit_arg_wins(clean_env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    assert resolve_api_key("gemini", api_key="explicit") == "explicit"


def test_env_var_used_when_no_arg(clean_env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    assert resolve_api_key("gemini") == "env-key"


def test_missing_key_raises_keyerror(clean_env):
    with pytest.raises(KeyError) as exc:
        resolve_api_key("gemini")
    assert "GEMINI_API_KEY" in str(exc.value)


def test_unknown_provider_raises_keyerror_with_uppercase_hint(clean_env):
    """Unknown providers raise KeyError whose message names the {PROVIDER}_API_KEY
    convention so the caller can fix their env, but resolve_api_key doesn't
    actually probe that var (only registered providers are checked)."""
    with pytest.raises(KeyError) as exc:
        resolve_api_key("custom")
    assert "CUSTOM_API_KEY" in str(exc.value)


@pytest.mark.parametrize("provider,env_var", [
    ("gemini",     "GEMINI_API_KEY"),
    ("anthropic",  "ANTHROPIC_API_KEY"),
    ("openai",     "OPENAI_API_KEY"),
    ("together",   "TOGETHER_API_KEY"),
    ("groq",       "GROQ_API_KEY"),
    ("openrouter", "OPENROUTER_API_KEY"),
])
def test_every_registered_provider_resolves_via_env(clean_env, monkeypatch, provider, env_var):
    """Regression: openrouter was missing from the map → provider_has_key was always False."""
    monkeypatch.setenv(env_var, "k")
    assert resolve_api_key(provider) == "k"


def test_base_url_explicit_overrides_default():
    assert resolve_base_url("together", base_url="https://custom/v1") == "https://custom/v1"


def test_base_url_uses_builtin_default():
    assert resolve_base_url("together") == "https://api.together.xyz/v1"
    assert resolve_base_url("groq") == "https://api.groq.com/openai/v1"
    assert resolve_base_url("openrouter") == "https://openrouter.ai/api/v1"


def test_base_url_unknown_provider_returns_none():
    assert resolve_base_url("some-unknown-provider") is None