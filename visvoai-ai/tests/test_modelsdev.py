"""Tests for the models.dev adapter: record → ModelDefinition, with the provider gate."""
from visvoai.ai.catalog.sources.modelsdev import (
    ModelsDevSource,
    to_definitions,
)
from visvoai.ai.model_registry import Capability


def _model(mid, *, tool=True, reasoning=False, cost_in=1.0, ctx=1000, text=True):
    mods = {"input": ["text"], "output": ["text"]} if text else {"input": ["image"], "output": ["text"]}
    return {
        "id": mid, "name": mid.upper(), "tool_call": tool, "reasoning": reasoning,
        "modalities": mods, "limit": {"context": ctx, "output": 100},
        "cost": {"input": cost_in, "output": cost_in * 2, "cache_read": 0.01},
    }


# A trimmed api.json covering every gate branch.
CATALOG = {
    # pure @ai-sdk/openai-compatible, has api → base_url from api
    "deepseek": {"npm": "@ai-sdk/openai-compatible", "api": "https://api.deepseek.com",
                 "env": ["DEEPSEEK_API_KEY"], "models": {"deepseek-chat": _model("deepseek-chat", reasoning=True)}},
    # branded, no api → base_url from BRANDED_BASE_URL, aliased to "together"
    "togetherai": {"npm": "@ai-sdk/togetherai", "env": ["TOGETHER_API_KEY"],
                   "models": {"some/model": _model("some/model")}},
    # bespoke message-format → dropped entirely
    "anthropic": {"npm": "@ai-sdk/anthropic", "env": ["ANTHROPIC_API_KEY"],
                  "models": {"claude-x": _model("claude-x")}},
    # openai-compatible but no key env → dropped
    "nokey": {"npm": "@ai-sdk/openai-compatible", "api": "https://x/v1", "env": [],
              "models": {"m": _model("m")}},
    # image-only model under a valid provider → that model dropped, provider kept
    "imgonly": {"npm": "@ai-sdk/openai-compatible", "api": "https://y/v1", "env": ["Y_API_KEY"],
                "models": {"img": _model("img", text=False)}},
    # branded npm BUT has an api endpoint (the OpenRouter case) → admitted by callability
    "openrouter": {"npm": "@openrouter/ai-sdk-provider", "api": "https://openrouter.ai/api/v1",
                   "env": ["OPENROUTER_API_KEY"], "models": {"x-ai/grok": _model("x-ai/grok")}},
}


def test_branded_npm_with_api_is_admitted():
    # npm is NOT @ai-sdk/openai-compatible, but it has an `api` → callable, so admitted.
    defs = {d.api_id: d for d in to_definitions(CATALOG)}
    assert "x-ai/grok" in defs
    assert defs["x-ai/grok"].base_url == "https://openrouter.ai/api/v1"
    assert defs["x-ai/grok"].provider == "openrouter"


def test_pure_openai_compat_uses_api_base_url():
    defs = {d.api_id: d for d in to_definitions(CATALOG)}
    ds = defs["deepseek-chat"]
    assert ds.provider == "deepseek"
    assert ds.base_url == "https://api.deepseek.com"
    assert ds.key_env == "DEEPSEEK_API_KEY"
    assert ds.supports_thinking is True
    assert ds.capabilities == [Capability.CHAT]


def test_branded_uses_mapped_base_url_and_alias():
    defs = {(d.provider, d.api_id): d for d in to_definitions(CATALOG)}
    t = defs[("together", "some/model")]   # togetherai aliased → together
    assert t.base_url == "https://api.together.xyz/v1"
    assert t.key_env == "TOGETHER_API_KEY"


def test_bespoke_provider_is_dropped():
    ids = {d.api_id for d in to_definitions(CATALOG)}
    assert "claude-x" not in ids  # anthropic sourced from baked, not models.dev


def test_provider_without_key_is_dropped():
    ids = {d.api_id for d in to_definitions(CATALOG)}
    assert "m" not in ids


def test_image_only_model_dropped_text_kept():
    ids = {d.api_id for d in to_definitions(CATALOG)}
    assert "img" not in ids


def test_source_wraps_to_definitions():
    src = ModelsDevSource(CATALOG)
    assert {d.api_id for d in src.models()} == {"deepseek-chat", "some/model", "x-ai/grok"}


def test_costs_and_context_mapped():
    ds = next(d for d in to_definitions(CATALOG) if d.api_id == "deepseek-chat")
    assert ds.input_cost_per_million == 1.0
    assert ds.output_cost_per_million == 2.0
    assert ds.cache_read_cost_per_million == 0.01
    assert ds.context_window == 1000
