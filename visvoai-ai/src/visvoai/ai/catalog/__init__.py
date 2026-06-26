"""
catalog — the model-catalog engine + its sources.

`engine` builds a validated `list[ModelDefinition]` from a stack of sources
(merge → gate → validate). Each source lives under `catalog.sources`. The public
`from visvoai.ai import build_catalog` surface re-exports from here.
"""
from visvoai.ai.catalog.engine import (
    BakedSource,
    CatalogSource,
    Gate,
    build_catalog,
    validate,
)
from visvoai.ai.catalog.sources.modelsdev import ModelsDevSource, to_definitions
from visvoai.ai.catalog.sources.remote import RemoteModelsDevSource

__all__ = [
    "CatalogSource", "BakedSource", "Gate", "build_catalog", "validate",
    "ModelsDevSource", "to_definitions", "RemoteModelsDevSource",
]
