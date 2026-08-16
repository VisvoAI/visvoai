"""
catalog.corrections — the handful of facts models.dev does not model.

models.dev is authoritative for what it carries: context window, token pricing,
reasoning support, tool calling. It has no concept of Google Search grounding
pricing, of our Capability routing, or of which model a keyless install should
default to. Those are laid over the live facts here rather than forking them.

This is deliberately narrow. What belongs here is what upstream *cannot* know.
What does NOT belong here is a fact upstream has and we disagree with — fix that
upstream, or it silently rots into a private fork of the catalog.

Usage:

    build_catalog(
        [BakedSource(), RemoteModelsDevSource(cache)],
        corrections=CURATED_CORRECTIONS,
    )

Ordering note: models.dev wins the merge wholesale over the baked entry for the
same id, which is the point — the live facts replace the hand-written ones — and
then these corrections restore the curated fields on top. Models the baked source
has and models.dev does not (a retired preview, an Imagen entry) are untouched by
either step and survive as-is.
"""
from typing import Any, Dict, Tuple

from visvoai.ai.model_registry import Capability

# {(provider, api_id): {field: value}}
CURATED_CORRECTIONS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("gemini", "gemini-3.7-flash"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH], "default_thinking_label": 'Think', "default": True},
    ("gemini", "gemini-3.6-flash"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-3.5-flash"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-3.1-pro-preview"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-3.1-pro-preview-customtools"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-3.1-flash-lite"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-3.1-flash-live-preview"): {"search_query_cost": 0.014},
    ("gemini", "gemini-3-flash-preview"): {"search_query_cost": 0.014, "capabilities": [Capability.CHAT, Capability.SEARCH], "default_thinking_label": 'Think'},
    ("gemini", "gemini-3-pro-image"): {"search_query_cost": 0.014},
    ("gemini", "gemini-3-pro-image-preview"): {"search_query_cost": 0.014, "deprecated": True},
    ("gemini", "gemini-2.5-pro"): {"search_query_cost": 0.035, "search_billed_per_request": True, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-2.5-flash"): {"search_query_cost": 0.035, "search_billed_per_request": True, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-2.5-flash-lite"): {"search_query_cost": 0.035, "search_billed_per_request": True, "capabilities": [Capability.CHAT, Capability.SEARCH]},
    ("gemini", "gemini-2.5-flash-preview-tts"): {"capabilities": [Capability.AUDIO_GEN]},
    ("gemini", "gemini-embedding-2"): {"capabilities": [Capability.EMBEDDING]},
}
