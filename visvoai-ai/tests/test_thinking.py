"""Tests for the thinking enum + per-mechanism translation."""
import pytest

from visvoai.ai.thinking import (
    ThinkingLevel, ThinkingMechanism, resolve_level, thinking_kwargs,
)

M = ThinkingMechanism
L = ThinkingLevel


def test_high_maps_per_mechanism():
    assert thinking_kwargs(M.GEMINI_LEVEL, L.HIGH) == {"thinking_level": "high", "include_thoughts": True}
    assert thinking_kwargs(M.GEMINI_BUDGET, L.HIGH) == {"thinking_budget": 8192, "include_thoughts": True}
    assert thinking_kwargs(M.ANTHROPIC_BUDGET, L.HIGH) == {"thinking": {"type": "enabled", "budget_tokens": 16000}}


def test_anthropic_adaptive_emits_adaptive_not_budget():
    # 4.6+ dialect: adaptive thinking, never legacy budget_tokens (which 400s on 4.6+).
    assert thinking_kwargs(M.ANTHROPIC_ADAPTIVE, L.OFF) == {}      # omit param (disabled 400s on Fable 5)
    assert thinking_kwargs(M.ANTHROPIC_ADAPTIVE, L.HIGH) == {"thinking": {"type": "adaptive"}}
    assert thinking_kwargs(M.ANTHROPIC_ADAPTIVE, L.LOW) == {"thinking": {"type": "adaptive"}}


def test_mechanism_routes_claude_by_version():
    from visvoai.ai.deployments import _mechanism
    from visvoai.ai.model_registry import ModelDefinition

    def md(api_id):
        return ModelDefinition(api_id=api_id, display_name=api_id, provider="anthropic",
                               input_cost_per_million=1, output_cost_per_million=1,
                               supports_thinking=True)

    # 4.6+ → adaptive
    assert _mechanism(md("claude-opus-4-8")) is M.ANTHROPIC_ADAPTIVE
    assert _mechanism(md("claude-sonnet-4-6")) is M.ANTHROPIC_ADAPTIVE
    assert _mechanism(md("claude-fable-5")) is M.ANTHROPIC_ADAPTIVE
    # legacy → budget
    assert _mechanism(md("claude-haiku-4-5")) is M.ANTHROPIC_BUDGET
    assert _mechanism(md("claude-3-5-sonnet-20241022")) is M.ANTHROPIC_BUDGET
    assert thinking_kwargs(M.OPENAI_EFFORT, L.HIGH) == {"reasoning_effort": "high"}
    assert thinking_kwargs(M.OPENAI_COMPAT_REASONING, L.HIGH) == {"reasoning_effort": "high"}
    assert thinking_kwargs(M.OPENROUTER_REASONING, L.HIGH) == {"reasoning": {"effort": "high"}}


def test_off_semantics():
    # Gemini OFF must be EXPLICIT 'minimal' — omitting defaults to high (cost trap)
    assert thinking_kwargs(M.GEMINI_LEVEL, L.OFF) == {"thinking_level": "minimal", "include_thoughts": False}
    assert thinking_kwargs(M.GEMINI_BUDGET, L.OFF) == {"thinking_budget": 0, "include_thoughts": False}
    # opt-in mechanisms: OFF == omit the param
    assert thinking_kwargs(M.ANTHROPIC_BUDGET, L.OFF) == {}
    assert thinking_kwargs(M.OPENAI_EFFORT, L.OFF) == {}
    assert thinking_kwargs(M.OPENROUTER_REASONING, L.OFF) == {}


def test_none_mechanism_is_always_empty():
    for lvl in L:
        assert thinking_kwargs(M.NONE, lvl) == {}


def test_resolve_level_is_drift_safe():
    assert resolve_level("high") is L.HIGH
    assert resolve_level(L.LOW) is L.LOW
    assert resolve_level(None) is L.OFF
    assert resolve_level(None, default=L.MEDIUM) is L.MEDIUM         # None → default
    assert resolve_level("garbage", default=L.MEDIUM) is L.MEDIUM    # unknown → default (no error)
