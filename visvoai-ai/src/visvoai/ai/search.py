"""
search.py — public grounded web-search entry point.

run_search(query) resolves the default SEARCH-capable deployment from the registry
and dispatches to that provider's search() facade (Provider.search — optional,
NotSupported by default; implemented by a provider with native grounding such as
GeminiProvider via Google Search). It mirrors build_chat_model's
deployment -> provider resolution, but for the SEARCH capability instead of CHAT.

Resolution follows the registry's curated default (default_deployment(SEARCH))
rather than a hardcoded provider, so it tracks whatever the default search model is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from visvoai.ai.deployments import default_deployment, get_deployment
from visvoai.ai.identity import DEFAULT_CODEC, IdentityCodec
from visvoai.ai.model_registry import Capability
from visvoai.ai.providers.factory import get_provider


class FetchError(Exception):
    """A URL fetch failed, was blocked, or returned no extractable text. Carries a
    user-facing reason — consumers surface .args[0] rather than a stack trace."""


@dataclass
class SearchSource:
    """One grounded source — where a claim in the answer came from."""
    title: str
    url: str
    snippet: str = ""


@dataclass
class SearchResult:
    """A grounded answer: synthesized prose plus the sources it was grounded on,
    and the search queries the model actually fired."""
    text: str
    sources: List[SearchSource] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)


def run_search(
    query: str,
    *,
    deployment_id: Optional[str] = None,
    provider: Optional[str] = None,
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    codec: IdentityCodec = DEFAULT_CODEC,
) -> SearchResult:
    """Grounded web search. Resolves the SEARCH-capable deployment and dispatches to
    its provider's search(). Resolution: an explicit `deployment_id` wins; else the
    SEARCH default, scoped to `provider` when given (the active provider's search
    model), else the global default.

    Raises ValueError if no deployment serves SEARCH or the id is unknown; the
    provider raises NotSupported if it has no grounded-search capability.
    """
    deployment_id = deployment_id or default_deployment(
        Capability.SEARCH, codec, provider=provider)
    if not deployment_id:
        raise ValueError("no deployment serves the SEARCH capability")
    dep = get_deployment(deployment_id, codec)
    if dep is None:
        raise ValueError(f"unknown deployment id: {deployment_id!r}")
    return get_provider(dep.provider).search(
        query, slug=dep.slug, api_key=api_key, system=system,
    )


def fetch_url(
    url: str,
    *,
    deployment_id: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    codec: IdentityCodec = DEFAULT_CODEC,
) -> str:
    """Fetch one URL and return its content as clean markdown, via the provider's
    native URL retrieval (e.g. Gemini URL Context — fetched server-side, not on the
    caller's machine). Resolution mirrors run_search: explicit deployment_id wins,
    else the SEARCH default scoped to `provider`, else the global default.

    Raises ValueError if no deployment serves it; NotSupported if the provider has
    no URL-fetch capability; FetchError on a failed/blocked/empty retrieval.
    """
    deployment_id = deployment_id or default_deployment(
        Capability.SEARCH, codec, provider=provider)
    if not deployment_id:
        raise ValueError("no deployment serves the SEARCH capability")
    dep = get_deployment(deployment_id, codec)
    if dep is None:
        raise ValueError(f"unknown deployment id: {deployment_id!r}")
    return get_provider(dep.provider).fetch_url(url, slug=dep.slug, api_key=api_key)
