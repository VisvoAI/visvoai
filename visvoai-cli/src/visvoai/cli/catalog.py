"""
visvoai.cli.catalog — install the dynamic model catalog for the CLI.

Stacks the baked floor under a cached models.dev fetch and installs it as the process
default, so the model picker reflects the live catalog (~4000 models / ~128 providers)
instead of only the baked list. Offline-tolerant: `RemoteModelsDevSource` serves the
on-disk cache, then the package's bundled snapshot, then nothing — so a failed/absent
network degrades to the baked floor and never blocks startup.

Called once from `_bootstrap_env` (after keys load). The picker filters to providers you
have a key for (see agent.chat_deployments) so abundance doesn't drown the list.
"""
from __future__ import annotations

import logging
from pathlib import Path

from visvoai.ai import BakedSource, build_catalog, install_catalog
from visvoai.ai.catalog import RemoteModelsDevSource
from visvoai.cli.store import visvoai_home

logger = logging.getLogger(__name__)


def models_cache_path() -> Path:
    """Where the models.dev fetch is cached (~/.visvoai/cache/models.json)."""
    return visvoai_home() / "cache" / "models.json"


def install_cli_catalog(*, force_refresh: bool = False) -> int:
    """Build + install [baked → cached models.dev] as the default registry. Returns the
    model count (0 if it degraded to baked). `force_refresh` drops the cache first so
    models.dev is re-fetched. Never raises — a catalog failure leaves the baked default."""
    cache = models_cache_path()
    if force_refresh:
        cache.unlink(missing_ok=True)
    try:
        defs = build_catalog([BakedSource(), RemoteModelsDevSource(cache)])
        install_catalog(defs)
        return len(defs)
    except Exception as e:  # boundary: never block the CLI on catalog assembly
        logger.warning("catalog install failed (%s) — using baked floor", e)
        return 0
