"""Tests for the composite deployment identity codec."""
import pytest

from visvoai.ai.identity import ColonAtCodec, DeploymentId, IdentityCodec


CASES = [
    ("gemini", "gemini-3-flash", "medium"),
    ("together", "llama-3.3-70b", None),
    ("openrouter", "meta-llama/llama-3.3-70b", "high"),   # slug contains '/'
    ("openai", "gpt-5", "low"),
]


@pytest.mark.parametrize("provider,model,effort", CASES)
def test_round_trip(provider, model, effort):
    c = ColonAtCodec()
    assert c.parse(c.build(provider, model, effort)) == DeploymentId(provider, model, effort)


def test_no_effort_omits_at():
    assert ColonAtCodec().build("groq", "llama-3.3-70b") == "groq:llama-3.3-70b"
    assert ColonAtCodec().build("groq", "llama-3.3-70b", "high") == "groq:llama-3.3-70b@high"


def test_parse_splits_first_colon_and_at():
    # provider split is the FIRST colon; slug '/' is preserved
    assert ColonAtCodec().parse("openrouter:anthropic/claude-opus-4@high") == \
        DeploymentId("openrouter", "anthropic/claude-opus-4", "high")


@pytest.mark.parametrize("bad", ["nocolon", "prov:", ":model", "prov:model@"])
def test_malformed_raises(bad):
    with pytest.raises(ValueError):
        ColonAtCodec().parse(bad)


def test_build_requires_parts():
    with pytest.raises(ValueError):
        ColonAtCodec().build("", "model")
    with pytest.raises(ValueError):
        ColonAtCodec().build("provider", "")


def test_codec_satisfies_protocol():
    assert isinstance(ColonAtCodec(), IdentityCodec)
