"""Tests for the public grounded-search seam: run_search resolves a SEARCH
deployment and dispatches to provider.search; default_deployment honors a provider
filter; the base Provider.search raises NotSupported."""
import pytest

import visvoai.ai.search as search
from visvoai.ai import SearchResult, SearchSource, run_search, fetch_url
from visvoai.ai.model_registry import Capability
from visvoai.ai.deployments import default_deployment
from visvoai.ai.providers.base import NotSupported, Provider


class _FakeProvider:
    """Records the search()/fetch_url() call and returns a canned result."""
    def __init__(self, sink):
        self._sink = sink

    def search(self, query, *, slug, api_key=None, system=None):
        self._sink.update(query=query, slug=slug, api_key=api_key, system=system)
        return SearchResult(text="grounded answer",
                            sources=[SearchSource(title="T", url="http://x")])

    def fetch_url(self, url, *, slug, api_key=None):
        self._sink.update(url=url, slug=slug, api_key=api_key)
        return "# Page\n\nclean markdown"


@pytest.fixture
def captured(monkeypatch):
    sink = {}
    monkeypatch.setattr(search, "get_provider",
                        lambda name: (sink.update(provider=name) or _FakeProvider(sink)))
    return sink


def test_run_search_resolves_default_and_dispatches(captured):
    result = run_search("who won?")
    # SEARCH default is a Gemini deployment → provider gemini, its wire slug.
    assert captured["provider"] == "gemini"
    assert captured["slug"].startswith("gemini-")
    assert captured["query"] == "who won?"
    assert result.text == "grounded answer"
    assert result.sources[0].url == "http://x"


def test_run_search_explicit_deployment_wins(captured):
    run_search("q", deployment_id="gemini:gemini-3-flash-preview")
    assert captured["slug"] == "gemini-3-flash-preview"


def test_run_search_unknown_deployment_raises(captured):
    with pytest.raises(ValueError):
        run_search("q", deployment_id="nope:missing")


def test_default_deployment_provider_filter():
    # Provider-scoped default resolves only that provider's SEARCH deployments.
    gem = default_deployment(Capability.SEARCH, provider="gemini")
    assert gem is not None and gem.startswith("gemini:")
    # A provider with no SEARCH-capable deployment → None.
    assert default_deployment(Capability.SEARCH, provider="nonexistent") is None


def test_base_provider_search_not_supported():
    with pytest.raises(NotSupported):
        Provider().search("q", slug="x")


def test_fetch_url_resolves_default_and_dispatches(captured):
    out = fetch_url("https://example.com")
    assert captured["provider"] == "gemini"
    assert captured["url"] == "https://example.com"
    assert out == "# Page\n\nclean markdown"


def test_fetch_url_unknown_deployment_raises(captured):
    with pytest.raises(ValueError):
        fetch_url("https://x", deployment_id="nope:missing")


def test_base_provider_fetch_url_not_supported():
    with pytest.raises(NotSupported):
        Provider().fetch_url("https://x", slug="x")
