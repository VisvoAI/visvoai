"""
catalog.engine — the catalog engine: turn a stack of sources into a validated model list.

A *source* yields `ModelDefinition`s. `build_catalog` stacks sources (later wins),
drops models whose provider we can't call (the gate), and validates the result. The
output is a plain `list[ModelDefinition]` — the SAME type `deployments.py` already
consumes, so the merged catalog is a drop-in replacement for the static `MODELS` list.

Offline-pure: no network, no disk knowledge here. A network-backed source (models.dev)
is a separate module the consumer opts into and feeds its own cache path.

Merge is wholesale per `(provider, api_id)`: later sources replace earlier entries for
the same key, and add new keys. Per-field merge is intentionally NOT done — the curation
surface that needed it (`default`, `enabled`) moved to app config / automatic filtering,
so a later source either replaces a model wholesale (override) or contributes a new one.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Tuple

from visvoai.ai.identity import DEFAULT_CODEC
from visvoai.ai.model_registry import MODELS as _BAKED, ModelDefinition

logger = logging.getLogger(__name__)

_Key = Tuple[str, str]  # (provider, api_id) — the merge/identity key


def _key(md: ModelDefinition) -> _Key:
    return (md.provider, md.api_id)


def _id_encodable(md: ModelDefinition) -> bool:
    """True if this model's deployment id round-trips through the codec. Some
    upstream slugs (e.g. cloudflare's '@cf/…', which starts with the codec's '@'
    effort marker) can't be encoded — admitting them is a landmine: they list but
    crash on get_deployment. Drop them at build time instead."""
    try:
        DEFAULT_CODEC.parse(DEFAULT_CODEC.build(md.provider, md.api_id))
        return True
    except Exception:
        return False


class CatalogSource(ABC):
    """A provider of model definitions. May do I/O internally (e.g. read a cache);
    the ABC imposes no I/O — it just yields the definitions this source contributes."""

    @abstractmethod
    def models(self) -> List[ModelDefinition]:
        ...


class BakedSource(CatalogSource):
    """The in-package floor. Defaults to the registry's `MODELS` — always present,
    works offline, and is what every consumer stacks everything else on top of."""

    def __init__(self, models: Optional[List[ModelDefinition]] = None) -> None:
        self._models = list(_BAKED if models is None else models)

    def models(self) -> List[ModelDefinition]:
        return list(self._models)


# Gate: a predicate deciding whether a model's provider is actually callable. The
# default trusts every entry (the baked list is wired by construction). The models.dev
# adapter gates at adapt time; a consumer can pass a stricter gate here too.
Gate = Callable[[ModelDefinition], bool]


def _merge(sources: List[CatalogSource]) -> List[ModelDefinition]:
    merged: Dict[_Key, ModelDefinition] = {}
    for src in sources:
        for md in src.models():
            merged[_key(md)] = md  # later source wins wholesale
    return list(merged.values())


def validate(defs: List[ModelDefinition]) -> None:
    """Fail loudly on a structurally broken catalog. Runs after merge (the old
    import-time checks lived in model_registry; they move here now that the list is
    dynamic). NB: no 'exactly one default' check — selection is app config now."""
    seen: set[_Key] = set()
    for md in defs:
        k = _key(md)
        if k in seen:
            raise ValueError(f"duplicate catalog entry for {k[0]}:{k[1]}")
        seen.add(k)
        if md.input_cost_per_million < 0 or md.output_cost_per_million < 0:
            raise ValueError(f"negative cost on {k[0]}:{k[1]}")
        if md.context_window < 0:
            raise ValueError(f"negative context_window on {k[0]}:{k[1]}")


def build_catalog(
    sources: List[CatalogSource],
    gate: Optional[Gate] = None,
) -> List[ModelDefinition]:
    """Stack sources (later wins) → gate → validate → final `list[ModelDefinition]`.

    `gate` drops models whose provider we can't call; dropped models are logged, not
    raised. With no gate, every merged model is kept (baked is callable by construction).
    """
    merged = _merge(sources)
    if gate is not None:
        kept, dropped = [], 0
        for md in merged:
            if gate(md):
                kept.append(md)
            else:
                dropped += 1
                logger.info("catalog: dropped %s:%s (provider not callable)", md.provider, md.api_id)
        if dropped:
            logger.info("catalog: %d model(s) dropped by gate", dropped)
        merged = kept
    # Drop models whose id can't be encoded by the codec — they'd list but crash on
    # get_deployment (a landmine in the picker). Filter once here, across all sources.
    encodable = [md for md in merged if _id_encodable(md)]
    if len(encodable) != len(merged):
        logger.info("catalog: dropped %d model(s) with non-encodable ids", len(merged) - len(encodable))
    merged = encodable
    validate(merged)
    return merged
