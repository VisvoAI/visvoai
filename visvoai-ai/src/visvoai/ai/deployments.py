"""
deployments.py — Model / Deployment layer (registry v2).

A *Model* is an intrinsic, provider-agnostic identity ("llama-3.3-70b"). A
*Deployment* is that model served by a specific provider — the billable, callable
unit, identified by a composite id ("together:llama-3.3-70b"). One Model has many
Deployments (Together, Groq, OpenRouter); the link is Deployment.model → Model.id.

Source of truth for rate-card data is the flat MODELS list in model_registry.py
(each entry = one provider's serving of a model). This module derives the clean
Model/Deployment view from it + an explicit MERGES map (which entries are the same
underlying model across providers), and exposes a small read-only DeploymentInfo
projection — the ONLY model-data type consumers should touch. Model and Deployment
themselves (with slug + thinking mechanism) are internal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from visvoai.ai.identity import DEFAULT_CODEC, IdentityCodec
from visvoai.ai.model_registry import MODELS as _RAW, Capability, ModelDefinition


class ThinkingMechanism(str, Enum):
    """How a deployment exposes reasoning. The provider facade translates a neutral
    intent (off|low|medium|high) into the right API kwargs per mechanism."""
    NONE = "none"
    GEMINI_LEVEL = "gemini_level"            # Gemini 3+: thinking_level enum
    GEMINI_BUDGET = "gemini_budget"          # Gemini 2.x: thinking_budget int
    ANTHROPIC_BUDGET = "anthropic_budget"    # Claude: extended thinking budget_tokens
    OPENAI_EFFORT = "openai_effort"          # OpenAI o-series/gpt-5: reasoning_effort
    OPENAI_COMPAT_REASONING = "openai_compat_reasoning"  # Together/Groq compat reasoning
    OPENROUTER_REASONING = "openrouter_reasoning"        # OpenRouter `reasoning` field


# Neutral thinking intents (the only thinking vocabulary consumers/UI see).
INTENTS = ("off", "low", "medium", "high")
_LABEL_TO_INTENT = {"Think": "medium", "Think Hard": "high"}


@dataclass(frozen=True)
class Model:
    """Intrinsic, provider-agnostic identity. Internal source-of-truth type."""
    id: str
    display_name: str
    family: str
    capabilities: List[Capability]
    reasoning: bool = False


@dataclass(frozen=True)
class Deployment:
    """A Model served by one provider — the billable/callable unit. Internal."""
    model: str                 # → Model.id
    provider: str
    slug: str                  # provider_model_id: the exact API string
    input_cost_per_million: float
    output_cost_per_million: float
    cache_read_cost_per_million: float = 0.0
    thinking: ThinkingMechanism = ThinkingMechanism.NONE
    default_intent: Optional[str] = None     # None = off
    capabilities: List[Capability] = field(default_factory=lambda: [Capability.CHAT])
    enabled: bool = True
    deprecated: bool = False
    default: bool = False

    def id(self, codec: IdentityCodec = DEFAULT_CODEC) -> str:
        return codec.build(self.provider, self.model)


@dataclass(frozen=True)
class DeploymentInfo:
    """Public read-only projection — the ONLY model-data type consumers touch.
    Omits slug + thinking mechanism (internal mechanics)."""
    id: str
    model: str
    display_name: str
    provider: str
    family: str
    capabilities: List[Capability]
    reasoning: bool
    input_cost_per_million: float
    output_cost_per_million: float
    thinking_default: Optional[str]   # neutral intent or None


# ── derivation: raw ModelDefinition → Model + Deployment ─────────────────────

# (provider, api_id) → canonical Model id, for entries that are the SAME underlying
# model across providers. Anything not listed uses its api_id as the model id (1:1).
_MERGES: Dict[tuple, str] = {
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): "llama-3.3-70b",
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"): "llama-3.3-70b",
}

# Display names for merged models (the per-deployment display_name varies, so pick one).
_MERGED_DISPLAY: Dict[str, str] = {"llama-3.3-70b": "Llama 3.3 70B"}


def _model_id(md: ModelDefinition) -> str:
    return _MERGES.get((md.provider, md.api_id), md.api_id)


def _mechanism(md: ModelDefinition) -> ThinkingMechanism:
    if not md.supports_thinking:
        return ThinkingMechanism.NONE
    p = md.provider
    if p == "gemini":
        is_g2 = md.api_id.startswith(("gemini-2.", "gemini-2-"))
        return ThinkingMechanism.GEMINI_BUDGET if is_g2 else ThinkingMechanism.GEMINI_LEVEL
    if p == "anthropic":
        return ThinkingMechanism.ANTHROPIC_BUDGET
    if p == "openai":
        return ThinkingMechanism.OPENAI_EFFORT
    if p == "openrouter":
        return ThinkingMechanism.OPENROUTER_REASONING
    return ThinkingMechanism.OPENAI_COMPAT_REASONING  # together/groq/other compat


def _default_intent(md: ModelDefinition) -> Optional[str]:
    if not md.supports_thinking:
        return None
    return _LABEL_TO_INTENT.get(md.default_thinking_label) if md.default_thinking_label else None


def _build() -> tuple[List[Model], List[Deployment]]:
    deployments: List[Deployment] = []
    models: Dict[str, Model] = {}
    for md in _RAW:
        mid = _model_id(md)
        deployments.append(Deployment(
            model=mid, provider=md.provider, slug=md.api_id,
            input_cost_per_million=md.input_cost_per_million,
            output_cost_per_million=md.output_cost_per_million,
            cache_read_cost_per_million=md.cache_read_cost_per_million,
            thinking=_mechanism(md), default_intent=_default_intent(md),
            capabilities=list(md.capabilities), enabled=md.enabled,
            deprecated=md.deprecated, default=md.default,
        ))
        if mid not in models:
            models[mid] = Model(
                id=mid,
                display_name=_MERGED_DISPLAY.get(mid, md.display_name),
                family=mid,
                capabilities=list(md.capabilities),
                reasoning=md.supports_thinking,
            )
    return list(models.values()), deployments


MODELS: List[Model]
DEPLOYMENTS: List[Deployment]
MODELS, DEPLOYMENTS = _build()

_MODEL_BY_ID = {m.id: m for m in MODELS}
_DEPLOYMENT_BY_KEY = {(d.provider, d.model): d for d in DEPLOYMENTS}
_DEPLOYMENTS_BY_MODEL: Dict[str, List[Deployment]] = {}
for _d in DEPLOYMENTS:
    _DEPLOYMENTS_BY_MODEL.setdefault(_d.model, []).append(_d)


# ── integrity (fail at import) ───────────────────────────────────────────────
for _d in DEPLOYMENTS:
    if _d.model not in _MODEL_BY_ID:
        raise RuntimeError(f"deployment {_d.provider}:{_d.model} references unknown model")
if len(_DEPLOYMENT_BY_KEY) != len(DEPLOYMENTS):
    raise RuntimeError("duplicate (provider, model) deployment key")
for _d in DEPLOYMENTS:
    if _d.default_intent is not None and _d.default_intent not in INTENTS:
        raise RuntimeError(f"deployment {_d.provider}:{_d.model} has bad default_intent {_d.default_intent!r}")


# ── lookups ──────────────────────────────────────────────────────────────────

def get_model(model_id: str) -> Optional[Model]:
    return _MODEL_BY_ID.get(model_id)


def get_deployment(deployment_id: str, codec: IdentityCodec = DEFAULT_CODEC) -> Optional[Deployment]:
    """Resolve a composite id ('provider:model[@effort]') to its Deployment."""
    parsed = codec.parse(deployment_id)
    return _DEPLOYMENT_BY_KEY.get((parsed.provider, parsed.model))


def deployments_for(model_id: str) -> List[Deployment]:
    return list(_DEPLOYMENTS_BY_MODEL.get(model_id, []))


def _to_info(d: Deployment, codec: IdentityCodec) -> DeploymentInfo:
    m = _MODEL_BY_ID[d.model]
    return DeploymentInfo(
        id=d.id(codec), model=d.model, display_name=m.display_name, provider=d.provider,
        family=m.family, capabilities=list(d.capabilities), reasoning=m.reasoning,
        input_cost_per_million=d.input_cost_per_million,
        output_cost_per_million=d.output_cost_per_million,
        thinking_default=d.default_intent,
    )


def list_deployments(capability: Optional[Capability] = None,
                     codec: IdentityCodec = DEFAULT_CODEC) -> List[DeploymentInfo]:
    """Public: selectable deployments as read-only DeploymentInfo (enabled, not
    deprecated). Filtered by capability when given."""
    out = []
    for d in DEPLOYMENTS:
        if not d.enabled or d.deprecated:
            continue
        if capability is not None and capability not in d.capabilities:
            continue
        out.append(_to_info(d, codec))
    return out


def get_deployment_info(deployment_id: str,
                        codec: IdentityCodec = DEFAULT_CODEC) -> Optional[DeploymentInfo]:
    d = get_deployment(deployment_id, codec)
    return _to_info(d, codec) if d else None


def default_deployment(capability: Capability = Capability.CHAT,
                       codec: IdentityCodec = DEFAULT_CODEC) -> Optional[str]:
    """Composite id of the default deployment for a capability (the `default=True`
    entry if it has the capability, else the first enabled one)."""
    for d in DEPLOYMENTS:
        if d.default and d.enabled and not d.deprecated and capability in d.capabilities:
            return d.id(codec)
    for d in DEPLOYMENTS:
        if d.enabled and not d.deprecated and capability in d.capabilities:
            return d.id(codec)
    return None
