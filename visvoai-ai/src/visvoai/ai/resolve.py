"""
resolve.py — the public resolver: deployment id → ready chat model + cost.

build_chat_model(deployment_id, level=…) is THE entry point consumers call. It
resolves the composite id to a Deployment, computes the provider thinking kwargs
from the chosen level (drift-safe, defaulting to the deployment's default), picks
the provider facade, and builds the model. Effort precedence:
    explicit level arg  >  the id's @effort  >  deployment.default_thinking  >  off
A raw thinking passthrough (thinking_raw) bypasses the enum for power users.
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel

from visvoai.ai.deployments import get_deployment
from visvoai.ai.identity import DEFAULT_CODEC, IdentityCodec
from visvoai.ai.providers.config import resolve_api_key
from visvoai.ai.providers.factory import get_provider
from visvoai.ai.thinking import resolve_level


def build_chat_model(
    deployment_id: str,
    *,
    level: Optional[str] = None,
    thinking_raw: Optional[dict] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    codec: IdentityCodec = DEFAULT_CODEC,
) -> BaseChatModel:
    """Resolve a composite deployment id to a configured, streaming chat model."""
    parsed = codec.parse(deployment_id)                 # raises on malformed
    dep = get_deployment(deployment_id, codec)
    if dep is None:
        raise ValueError(f"unknown deployment id: {deployment_id!r}")

    if thinking_raw is not None:
        extra = dict(thinking_raw)                       # power-user escape hatch
    else:
        chosen = level if level is not None else parsed.effort
        lvl = resolve_level(chosen, default=dep.default_thinking)
        extra = dep.thinking_kwargs(lvl)

    # Catalog-sourced deployments carry their own endpoint/key (provider not in the
    # static config maps). Resolve them to explicit args so the provider facade — which
    # is unchanged — uses them (explicit wins). Caller-passed base_url/api_key still win.
    eff_base_url = base_url if base_url is not None else dep.base_url
    eff_api_key = api_key
    if eff_api_key is None and dep.key_env:
        eff_api_key = resolve_api_key(dep.provider, env_var=dep.key_env)

    return get_provider(dep.provider).build(
        slug=dep.slug, api_key=eff_api_key, base_url=eff_base_url, **extra,
    )


def cost_of(deployment_id: str, input_tokens: int, output_tokens: int,
            codec: IdentityCodec = DEFAULT_CODEC) -> float:
    """USD cost of a call against a deployment's per-million rates."""
    dep = get_deployment(deployment_id, codec)
    if dep is None:
        raise ValueError(f"unknown deployment id: {deployment_id!r}")
    return (input_tokens / 1_000_000) * dep.input_cost_per_million + \
           (output_tokens / 1_000_000) * dep.output_cost_per_million
