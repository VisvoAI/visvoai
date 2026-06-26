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
from typing import Dict, List, Optional

from visvoai.ai.identity import DEFAULT_CODEC, IdentityCodec
from visvoai.ai.model_registry import (
    MODELS as _RAW,
    Capability,
    ModelDefinition,
    DEFAULT_MODEL_FOR as _DEFAULT_MODEL_FOR,
)
from visvoai.ai.thinking import (
    ThinkingLevel,
    ThinkingMechanism,
    thinking_kwargs as _thinking_kwargs,
)

# Registry's UI default label → coarse default ThinkingLevel.
_LABEL_TO_LEVEL = {"Think": ThinkingLevel.MEDIUM, "Think Hard": ThinkingLevel.HIGH}
_ALL_LEVELS = [ThinkingLevel.OFF, ThinkingLevel.LOW, ThinkingLevel.MEDIUM, ThinkingLevel.HIGH]


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
    context_window: int = 0    # max context tokens (0 = unknown → gauge hidden)
    cache_read_cost_per_million: float = 0.0
    thinking: ThinkingMechanism = ThinkingMechanism.NONE
    default_thinking: ThinkingLevel = ThinkingLevel.OFF
    capabilities: List[Capability] = field(default_factory=lambda: [Capability.CHAT])
    enabled: bool = True
    deprecated: bool = False
    default: bool = False

    def id(self, codec: IdentityCodec = DEFAULT_CODEC) -> str:
        return codec.build(self.provider, self.model)

    @property
    def supports_thinking(self) -> bool:
        return self.thinking is not ThinkingMechanism.NONE

    def thinking_levels(self) -> List[ThinkingLevel]:
        """The levels a UI should offer for this deployment ([] when unsupported)."""
        return list(_ALL_LEVELS) if self.supports_thinking else []

    def thinking_kwargs(self, level: ThinkingLevel) -> dict:
        """Translate a chosen level into this deployment's provider API kwargs."""
        return _thinking_kwargs(self.thinking, level)


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
    context_window: int                    # max context tokens (0 = unknown)
    supports_thinking: bool
    thinking_levels: List[ThinkingLevel]   # options to render (empty when unsupported)
    default_thinking: ThinkingLevel        # preselected option


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


def _default_level(md: ModelDefinition) -> ThinkingLevel:
    if md.supports_thinking and md.default_thinking_label:
        return _LABEL_TO_LEVEL.get(md.default_thinking_label, ThinkingLevel.OFF)
    return ThinkingLevel.OFF


# Approximate context windows by provider, used when a ModelDefinition doesn't pin
# its own context_window. Approximate by design (drives a UI gauge, not billing) —
# set context_window on a ModelDefinition to override per-model.
_PROVIDER_WINDOW: Dict[str, int] = {
    "gemini": 1_048_576,
    "anthropic": 200_000,
    "openai": 128_000,
    "together": 128_000,
    "openrouter": 128_000,
    "groq": 128_000,
}


def _window(md: ModelDefinition) -> int:
    return md.context_window or _PROVIDER_WINDOW.get(md.provider, 0)


def _build() -> tuple[List[Model], List[Deployment]]:
    deployments: List[Deployment] = []
    models: Dict[str, Model] = {}
    for md in _RAW:
        mid = _model_id(md)
        deployments.append(Deployment(
            model=mid, provider=md.provider, slug=md.api_id,
            input_cost_per_million=md.input_cost_per_million,
            output_cost_per_million=md.output_cost_per_million,
            context_window=_window(md),
            cache_read_cost_per_million=md.cache_read_cost_per_million,
            thinking=_mechanism(md), default_thinking=_default_level(md),
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
        context_window=d.context_window,
        supports_thinking=d.supports_thinking,
        thinking_levels=d.thinking_levels(),
        default_thinking=d.default_thinking,
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
    """Composite id of the default deployment for a capability. Precedence: the
    curated DEFAULT_MODEL_FOR pick (matched by provider wire slug) → the global
    `default=True` deployment → the first enabled one. Returns None if nothing
    serves the capability."""
    curated = _DEFAULT_MODEL_FOR.get(capability)
    if curated:
        for d in DEPLOYMENTS:
            if d.slug == curated and d.enabled and not d.deprecated and capability in d.capabilities:
                return d.id(codec)
    for d in DEPLOYMENTS:
        if d.default and d.enabled and not d.deprecated and capability in d.capabilities:
            return d.id(codec)
    for d in DEPLOYMENTS:
        if d.enabled and not d.deprecated and capability in d.capabilities:
            return d.id(codec)
    return None
