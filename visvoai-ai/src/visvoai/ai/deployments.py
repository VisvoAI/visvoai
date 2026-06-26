"""
deployments.py — Model / Deployment layer (registry v2).

A *Model* is an intrinsic, provider-agnostic identity ("llama-3.3-70b"). A
*Deployment* is that model served by a specific provider — the billable, callable
unit, identified by a composite id ("together:llama-3.3-70b"). One Model has many
Deployments (Together, Groq, OpenRouter); the link is Deployment.model → Model.id.

Rate-card data comes from a flat `list[ModelDefinition]` (each entry = one provider's
serving of a model). The clean Model/Deployment view is derived from it + an explicit
MERGES map (which entries are the same underlying model across providers), exposed via
a read-only DeploymentInfo projection — the ONLY model-data type consumers touch.

The derivation lives in `DeploymentRegistry`, built from a definition list. A module-level
default registry (`_default`) is built from the baked `model_registry.MODELS` and backs the
free functions below, so existing callers are unchanged. A consumer that wants a dynamic
catalog calls `install_catalog(build_catalog([...]))` once at startup to swap the default —
see catalog/. The object is the source of truth; the free functions are convenience over
the default instance (cf. logging.Logger + root logger).
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
    base_url: Optional[str] = None     # carried endpoint for catalog-sourced providers (None = static map)
    key_env: Optional[str] = None      # carried API-key env var name (None = static _ENV_KEY_MAP)

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
        # 4.6+ models take adaptive thinking; legacy budget_tokens 400s there. Older Claude
        # (Haiku 4.5, 3.5) keep the budget mechanism. Keyed by api_id prefix.
        _adaptive = ("claude-fable-", "claude-opus-4-6", "claude-opus-4-7",
                     "claude-opus-4-8", "claude-sonnet-4-6")
        return (ThinkingMechanism.ANTHROPIC_ADAPTIVE if md.api_id.startswith(_adaptive)
                else ThinkingMechanism.ANTHROPIC_BUDGET)
    if p == "openai":
        return ThinkingMechanism.OPENAI_EFFORT
    if p == "openrouter":
        return ThinkingMechanism.OPENROUTER_REASONING
    return ThinkingMechanism.OPENAI_COMPAT_REASONING  # together/groq/other compat


def _default_level(md: ModelDefinition) -> ThinkingLevel:
    if md.supports_thinking and md.default_thinking_label:
        return _LABEL_TO_LEVEL.get(md.default_thinking_label, ThinkingLevel.OFF)
    return ThinkingLevel.OFF




def _build(raw: List[ModelDefinition]) -> tuple[List[Model], List[Deployment]]:
    deployments: List[Deployment] = []
    models: Dict[str, Model] = {}
    for md in raw:
        mid = _model_id(md)
        deployments.append(Deployment(
            model=mid, provider=md.provider, slug=md.api_id,
            input_cost_per_million=md.input_cost_per_million,
            output_cost_per_million=md.output_cost_per_million,
            context_window=md.context_window,   # single source of truth on the definition
            cache_read_cost_per_million=md.cache_read_cost_per_million,
            thinking=_mechanism(md), default_thinking=_default_level(md),
            capabilities=list(md.capabilities), enabled=md.enabled,
            deprecated=md.deprecated, default=md.default,
            base_url=md.base_url, key_env=md.key_env,
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


# ── registry: the correct core (no global state; one instance per catalog) ────

class DeploymentRegistry:
    """The Model/Deployment view derived from a `list[ModelDefinition]`. Pure and
    instance-scoped — construct one per catalog, inject it, test it in isolation.
    The free functions below delegate to a module-level default instance."""

    def __init__(self, model_defs: List[ModelDefinition]) -> None:
        self.models, self.deployments = _build(list(model_defs))
        self._model_by_id = {m.id: m for m in self.models}
        self._deployment_by_key = {(d.provider, d.model): d for d in self.deployments}
        self._deployments_by_model: Dict[str, List[Deployment]] = {}
        for d in self.deployments:
            self._deployments_by_model.setdefault(d.model, []).append(d)
        self._check_integrity()

    def _check_integrity(self) -> None:
        for d in self.deployments:
            if d.model not in self._model_by_id:
                raise RuntimeError(f"deployment {d.provider}:{d.model} references unknown model")
        if len(self._deployment_by_key) != len(self.deployments):
            raise RuntimeError("duplicate (provider, model) deployment key")

    def get_model(self, model_id: str) -> Optional[Model]:
        return self._model_by_id.get(model_id)

    def get_deployment(self, deployment_id: str,
                       codec: IdentityCodec = DEFAULT_CODEC) -> Optional[Deployment]:
        """Resolve a composite id ('provider:model[@effort]') to its Deployment."""
        parsed = codec.parse(deployment_id)
        return self._deployment_by_key.get((parsed.provider, parsed.model))

    def deployments_for(self, model_id: str) -> List[Deployment]:
        return list(self._deployments_by_model.get(model_id, []))

    def _to_info(self, d: Deployment, codec: IdentityCodec) -> DeploymentInfo:
        m = self._model_by_id[d.model]
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

    def list_deployments(self, capability: Optional[Capability] = None,
                         codec: IdentityCodec = DEFAULT_CODEC) -> List[DeploymentInfo]:
        """Selectable deployments as read-only DeploymentInfo (enabled, not deprecated),
        filtered by capability when given."""
        out = []
        for d in self.deployments:
            if not d.enabled or d.deprecated:
                continue
            if capability is not None and capability not in d.capabilities:
                continue
            out.append(self._to_info(d, codec))
        return out

    def get_deployment_info(self, deployment_id: str,
                            codec: IdentityCodec = DEFAULT_CODEC) -> Optional[DeploymentInfo]:
        d = self.get_deployment(deployment_id, codec)
        return self._to_info(d, codec) if d else None

    def default_deployment(self, capability: Capability = Capability.CHAT,
                           codec: IdentityCodec = DEFAULT_CODEC,
                           provider: Optional[str] = None) -> Optional[str]:
        """Composite id of the default deployment for a capability, optionally scoped
        to one provider. Precedence: the curated DEFAULT_MODEL_FOR pick (matched by
        provider wire slug) → the global `default=True` deployment → the first enabled
        one. With `provider` set, only that provider's deployments are considered, and
        the curated pick only counts if it belongs to that provider. None if nothing serves it."""
        def _ok(d) -> bool:
            return (d.enabled and not d.deprecated and capability in d.capabilities
                    and (provider is None or d.provider == provider))

        curated = _DEFAULT_MODEL_FOR.get(capability)
        if curated:
            for d in self.deployments:
                if d.slug == curated and _ok(d):
                    return d.id(codec)
        for d in self.deployments:
            if d.default and _ok(d):
                return d.id(codec)
        for d in self.deployments:
            if _ok(d):
                return d.id(codec)
        return None


# ── default-instance shell: convenience over the one process-wide registry ────

_default = DeploymentRegistry(list(_RAW))


def get_default_registry() -> DeploymentRegistry:
    return _default


def set_default_registry(reg: DeploymentRegistry) -> None:
    """Swap the registry backing the free functions. The catalog seam: a consumer
    builds a merged catalog and installs it once at startup."""
    global _default
    _default = reg


def install_catalog(model_defs: List[ModelDefinition]) -> None:
    """Convenience: rebuild + install the default registry from a merged catalog
    (the output of catalog.build_catalog([...]))."""
    set_default_registry(DeploymentRegistry(model_defs))


def get_model(model_id: str) -> Optional[Model]:
    return _default.get_model(model_id)


def get_deployment(deployment_id: str, codec: IdentityCodec = DEFAULT_CODEC) -> Optional[Deployment]:
    return _default.get_deployment(deployment_id, codec)


def deployments_for(model_id: str) -> List[Deployment]:
    return _default.deployments_for(model_id)


def list_deployments(capability: Optional[Capability] = None,
                     codec: IdentityCodec = DEFAULT_CODEC) -> List[DeploymentInfo]:
    return _default.list_deployments(capability, codec)


def get_deployment_info(deployment_id: str,
                        codec: IdentityCodec = DEFAULT_CODEC) -> Optional[DeploymentInfo]:
    return _default.get_deployment_info(deployment_id, codec)


def default_deployment(capability: Capability = Capability.CHAT,
                       codec: IdentityCodec = DEFAULT_CODEC,
                       provider: Optional[str] = None) -> Optional[str]:
    return _default.default_deployment(capability, codec, provider)
