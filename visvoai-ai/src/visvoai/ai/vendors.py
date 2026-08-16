"""
vendors.py — who MADE a model, as distinct from who serves it.

Three things get called "provider" in casual use and they are not the same:

    vendor    who made the model            Google
    provider  who serves it (the route)     gemini (direct) | openrouter (router)
    slug      the string that route wants   gemini-3.7-flash | google/gemini-3.7-flash

A consumer picking a model wants to browse by *vendor* — "the Google models" is
a meaningful group, while "the OpenRouter models" is 340 models from thirty
vendors and means nothing. But only `provider` is carried explicitly, so vendor
has to be derived.

Aggregators namespace their slugs `vendor/model`, which is the signal. It needs
normalising: the same vendor appears as `qwen` and `Qwen`, as `meta-llama` and
`meta`, and OpenRouter prefixes some routes with `~`. First-party providers use
no namespace at all, so they map from the provider name instead.

Deliberately a best-effort derivation returning None rather than guessing: an
unknown vendor should render ungrouped, not under a wrong heading.
"""
from __future__ import annotations

from typing import Optional

# provider name → vendor, for first-party routes whose slugs carry no namespace.
# `gemini` is the route; `google` is who makes the model — the one case where
# our provider name and the vendor genuinely differ.
_FIRST_PARTY_VENDOR = {
    "gemini": "google",
    "anthropic": "anthropic",
    "openai": "openai",
}

# Namespace spellings that denote the same vendor. Left side is always already
# lowercased and `~`-stripped by _normalise().
_VENDOR_ALIAS = {
    "meta-llama": "meta",
    "mistralai": "mistral",
    "deepseek-ai": "deepseek",
    "zai-org": "z-ai",
    "minimaxai": "minimax",
    "moonshotai": "moonshot",
    "bytedance-seed": "bytedance",
    "nousresearch": "nous",
    "thinkingmachines": "thinking-machines",
    "inclusionai": "inclusion",
    "x-ai": "xai",
    "google-vertex": "google",
}

# Display names for vendors whose normalised id does not title-case well.
_VENDOR_LABEL = {
    "openai": "OpenAI",
    "xai": "xAI",
    "z-ai": "Z.AI",
    "deepseek": "DeepSeek",
    "minimax": "MiniMax",
    "nvidia": "NVIDIA",
    "ibm-granite": "IBM Granite",
    "ai21": "AI21",
    "liquid": "Liquid AI",
    "allenai": "Allen AI",
}


def _normalise(raw: str) -> str:
    # OpenRouter prefixes some routes "~anthropic"; the tilde is routing
    # metadata, not part of the vendor's name.
    return raw.strip().lstrip("~").lower()


def vendor_of(provider: str, slug: str) -> Optional[str]:
    """The vendor that makes this model, or None when it cannot be determined.

    `provider` is the serving route, `slug` the string that route expects.
    """
    if "/" in slug:
        prefix = _normalise(slug.split("/", 1)[0])
        if not prefix:
            return None
        return _VENDOR_ALIAS.get(prefix, prefix)
    return _FIRST_PARTY_VENDOR.get(provider)


def vendor_label(vendor: Optional[str]) -> Optional[str]:
    """Human-facing name for a vendor id, for a group heading."""
    if not vendor:
        return None
    if vendor in _VENDOR_LABEL:
        return _VENDOR_LABEL[vendor]
    # "meta" → "Meta", "bytedance" → "Bytedance", "aion-labs" → "Aion Labs"
    return " ".join(part.capitalize() for part in vendor.split("-"))
