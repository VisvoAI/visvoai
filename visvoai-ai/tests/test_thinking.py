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
