"""
catalog.sources.modelsdev — adapt the models.dev catalog into `ModelDefinition`s.

models.dev publishes one JSON document (`api.json`), keyed by provider id; each
provider carries `npm` (SDK package — the compatibility signal), `api` (endpoint),
`env` (key var names), and a `models` map of facts (cost, context, reasoning, …).

This source maps that into our `ModelDefinition`s for providers we can actually call.
Admission is by **callability, not npm**: if a provider exposes a Chat Completions
endpoint we can derive, we admit it. (npm is unreliable for this — OpenRouter ships a
branded `@openrouter/ai-sdk-provider` yet is plainly OpenAI-compatible with an `api`.)

    id in BESPOKE / DENY  → skipped (gemini/anthropic come from the baked source;
                            message-format providers — bedrock/cohere/azure — we can't call)
    has `api`             → OpenAI-compat. base_url = api, key_env = env[0]   (most providers)
    id in BRANDED_BASE_URL → OpenAI-compat. base_url = our map  (compat but `api` omitted upstream)
    otherwise             → skipped (no derivable base_url)

The provider gate is the whole manual surface (the constants below). Everything else
flows from models.dev untouched.

Pure: this takes an already-fetched dict (no network here — fetching/caching is the
consumer's job, see catalog.sources.remote).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from visvoai.ai.catalog.engine import CatalogSource
from visvoai.ai.model_registry import Capability, ModelDefinition

logger = logging.getLogger(__name__)

# models.dev provider id → our provider name, where they differ. Keeps catalog-sourced
# deployments under the same provider name as baked ones (avoids a duplicate "togetherai").
PROVIDER_ALIAS: Dict[str, str] = {"togetherai": "together"}

# Branded-but-compatible: OpenAI Chat Completions shaped, but models.dev omits `api`
# because their SDK hardcodes it. We supply the base_url. (Mirrors providers/config.py.)
BRANDED_BASE_URL: Dict[str, str] = {
    "togetherai": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "cerebras": "https://api.cerebras.ai/v1",
    "perplexity": "https://api.perplexity.ai",
}

# Providers we do NOT source from models.dev: bespoke message-format families (served by
# our own facade + the curated baked entries) and endpoints we can't call as Chat Completions.
BESPOKE_OR_DENY = {
    "anthropic", "google", "google-vertex", "google-vertex-anthropic",
    "amazon-bedrock", "azure", "azure-cognitive-services", "cohere", "sap-ai-core",
}

def _base_url(pid: str, rec: dict) -> Optional[str]:
    """Endpoint for an OpenAI-compat provider: models.dev `api` → branded map → None."""
    api = rec.get("api")
    if api:
        return api.rstrip("/")
    return BRANDED_BASE_URL.get(pid)


def _is_openai_compat(pid: str, rec: dict) -> bool:
    """Can we call this provider through the OpenAI-compat path? By callability, not npm:
    a derivable Chat Completions base_url (from `api` or the branded map) and not denied.
    'openai' itself has no `api` (library default) but is always callable."""
    if pid in BESPOKE_OR_DENY:
        return False
    if pid == "openai":
        return True
    return bool(rec.get("api")) or pid in BRANDED_BASE_URL


def _model_def(provider: str, base_url: Optional[str], key_env: Optional[str],
               m: dict) -> Optional[ModelDefinition]:
    """One models.dev model record → a ModelDefinition, or None if not text chat."""
    mods = m.get("modalities") or {}
    inputs = mods.get("input") or ["text"]
    outputs = mods.get("output") or ["text"]
    if "text" not in inputs or "text" not in outputs:
        return None  # image/audio-only — not a chat deployment
    cost = m.get("cost") or {}
    limit = m.get("limit") or {}
    return ModelDefinition(
        api_id=m["id"],
        display_name=m.get("name") or m["id"],
        provider=provider,
        input_cost_per_million=float(cost.get("input", 0.0) or 0.0),
        output_cost_per_million=float(cost.get("output", 0.0) or 0.0),
        cache_read_cost_per_million=float(cost.get("cache_read", 0.0) or 0.0),
        context_window=int(limit.get("context", 0) or 0),
        supports_thinking=bool(m.get("reasoning")),
        capabilities=[Capability.CHAT],
        base_url=base_url,
        key_env=key_env,
        enabled=True,
    )


def to_definitions(catalog: Dict[str, Any]) -> List[ModelDefinition]:
    """Map a parsed models.dev `api.json` → callable `ModelDefinition`s. Drops providers
    we can't call (logged), and non-text models."""
    out: List[ModelDefinition] = []
    dropped_providers = 0
    for pid, rec in catalog.items():
        if not _is_openai_compat(pid, rec):
            dropped_providers += 1
            logger.debug("modelsdev: skip provider %s (not OpenAI-compat / bespoke)", pid)
            continue
        base_url = _base_url(pid, rec)
        env = rec.get("env") or []
        if not base_url and pid != "openai":
            logger.info("modelsdev: skip %s — no derivable base_url", pid)
            continue
        if not env:
            logger.info("modelsdev: skip %s — no key env var", pid)
            continue
        provider = PROVIDER_ALIAS.get(pid, pid)
        for m in (rec.get("models") or {}).values():
            md = _model_def(provider, base_url, env[0], m)
            if md is not None:
                out.append(md)
    logger.info("modelsdev: %d definitions from %d providers (%d providers skipped)",
                len(out), len(catalog) - dropped_providers, dropped_providers)
    return out


class ModelsDevSource(CatalogSource):
    """A CatalogSource over an already-fetched models.dev `api.json` dict."""

    def __init__(self, catalog: Dict[str, Any]) -> None:
        self._catalog = catalog

    def models(self) -> List[ModelDefinition]:
        return to_definitions(self._catalog)
