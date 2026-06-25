"""
thinking.py — the thinking abstraction: a stable public enum + internal translation.

Consumers only ever speak `ThinkingLevel` (OFF/LOW/MEDIUM/HIGH) — one stable
control to render, one value to send. All provider/model churn is absorbed here:
each deployment declares a `ThinkingMechanism`, and `thinking_kwargs(mechanism,
level)` maps the fixed enum to that provider's actual API kwargs. New providers add
a mechanism + a branch here; the consumer contract never changes.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class ThinkingLevel(str, Enum):
    """The ONLY thinking vocabulary consumers see. Stable forever."""
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ThinkingMechanism(str, Enum):
    """How a deployment exposes reasoning (internal — never shown to consumers).
    Extensible: a new provider/API shape adds a member + a branch in thinking_kwargs."""
    NONE = "none"
    GEMINI_LEVEL = "gemini_level"                # Gemini 3+: thinking_level enum
    GEMINI_BUDGET = "gemini_budget"              # Gemini 2.x: thinking_budget int
    ANTHROPIC_BUDGET = "anthropic_budget"        # Claude: extended thinking budget_tokens
    OPENAI_EFFORT = "openai_effort"              # OpenAI o-series/gpt-5: reasoning_effort
    OPENAI_COMPAT_REASONING = "openai_compat_reasoning"  # Together/Groq compat reasoning
    OPENROUTER_REASONING = "openrouter_reasoning"        # OpenRouter `reasoning` field


# LOW/MEDIUM/HIGH → token budgets for the budget-style mechanisms.
_GEMINI_BUDGET = {ThinkingLevel.LOW: 1024, ThinkingLevel.MEDIUM: 4096, ThinkingLevel.HIGH: 8192}
_ANTHROPIC_BUDGET = {ThinkingLevel.LOW: 2000, ThinkingLevel.MEDIUM: 8000, ThinkingLevel.HIGH: 16000}


def resolve_level(value: Any, default: ThinkingLevel = ThinkingLevel.OFF) -> ThinkingLevel:
    """Normalize an incoming value to a ThinkingLevel — the drift-safe entry point.

    None or an unrecognized value → `default` (so a stale stored preference never
    errors; it degrades to the deployment's default). An explicit valid level wins.
    """
    if value is None:
        return default
    if isinstance(value, ThinkingLevel):
        return value
    try:
        return ThinkingLevel(str(value).lower())
    except ValueError:
        return default


def thinking_kwargs(mechanism: ThinkingMechanism, level: ThinkingLevel) -> Dict[str, Any]:
    """Translate (mechanism, level) → the provider's API kwargs. The single place
    every per-provider thinking quirk lives."""
    m, L = mechanism, level

    if m is ThinkingMechanism.NONE:
        return {}

    if m is ThinkingMechanism.GEMINI_LEVEL:
        # OFF must be EXPLICIT 'minimal' — omitting thinking_level defaults to high (cost!).
        if L is ThinkingLevel.OFF:
            return {"thinking_level": "minimal", "include_thoughts": False}
        return {"thinking_level": L.value, "include_thoughts": True}

    if m is ThinkingMechanism.GEMINI_BUDGET:
        if L is ThinkingLevel.OFF:
            return {"thinking_budget": 0, "include_thoughts": False}
        return {"thinking_budget": _GEMINI_BUDGET[L], "include_thoughts": True}

    if m is ThinkingMechanism.ANTHROPIC_BUDGET:
        if L is ThinkingLevel.OFF:
            return {}   # Claude thinking is opt-in; omitting the param = off
        return {"thinking": {"type": "enabled", "budget_tokens": _ANTHROPIC_BUDGET[L]}}

    if m in (ThinkingMechanism.OPENAI_EFFORT, ThinkingMechanism.OPENAI_COMPAT_REASONING):
        return {} if L is ThinkingLevel.OFF else {"reasoning_effort": L.value}

    if m is ThinkingMechanism.OPENROUTER_REASONING:
        return {} if L is ThinkingLevel.OFF else {"reasoning": {"effort": L.value}}

    return {}
