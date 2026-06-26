"""web_search / web_fetch CLI tools.

web_search formats run_search's grounded result + sources and degrades to an
ERROR string on missing key / unsupported provider. web_fetch resolves the default
model + key and reports a missing key as data (never raises). The live grounding /
URL-Context calls are not exercised here — those are smoke-test items."""
import visvoai.cli.tools as tools
from visvoai.ai import SearchResult, SearchSource
from visvoai.ai.providers.base import NotSupported


def _invoke(t, **kw):
    return t.invoke(kw)


def test_web_search_formats_answer_and_sources(monkeypatch):
    def fake_run_search(query, *, system=None, **kw):
        return SearchResult(
            text="Paris is the capital of France.",
            sources=[SearchSource(title="Britannica", url="https://b.com/paris"),
                     SearchSource(title="", url="https://x.com/p")],
        )
    monkeypatch.setattr("visvoai.ai.run_search", fake_run_search)

    out = _invoke(tools.web_search, query="capital of France")
    assert "Paris is the capital" in out
    assert "Sources:" in out
    assert "[1] Britannica — https://b.com/paris" in out
    # Source with no title falls back to the URL as its label.
    assert "[2] https://x.com/p — https://x.com/p" in out


def test_web_search_missing_key_is_error_string(monkeypatch):
    def boom(query, *, system=None, **kw):
        raise KeyError("gemini")
    monkeypatch.setattr("visvoai.ai.run_search", boom)
    out = _invoke(tools.web_search, query="x")
    assert out.startswith("ERROR") and "GEMINI_API_KEY" in out


def test_web_search_unsupported_provider_is_error_string(monkeypatch):
    def nope(query, *, system=None, **kw):
        raise NotSupported("no grounding")
    monkeypatch.setattr("visvoai.ai.run_search", nope)
    out = _invoke(tools.web_search, query="x")
    assert out.startswith("ERROR") and "not available" in out


def test_web_search_empty_result(monkeypatch):
    monkeypatch.setattr("visvoai.ai.run_search",
                        lambda query, *, system=None, **kw: SearchResult(text=""))
    out = _invoke(tools.web_search, query="obscure")
    assert "No results found" in out


def test_web_fetch_returns_capped_markdown(monkeypatch):
    monkeypatch.setattr("visvoai.ai.fetch_url",
                        lambda url, **kw: "# Title\n\nsome page content")
    out = _invoke(tools.web_fetch, url="https://example.com")
    assert "# Title" in out and "some page content" in out


def test_web_fetch_missing_key_is_error_string(monkeypatch):
    def no_key(url, **kw):
        raise KeyError("gemini")
    monkeypatch.setattr("visvoai.ai.fetch_url", no_key)
    out = _invoke(tools.web_fetch, url="https://example.com")
    assert out.startswith("ERROR") and "GEMINI_API_KEY" in out


def test_web_fetch_fetch_error_suggests_search(monkeypatch):
    from visvoai.ai import FetchError

    def boom(url, **kw):
        raise FetchError("the page returned no extractable text")
    monkeypatch.setattr("visvoai.ai.fetch_url", boom)
    out = _invoke(tools.web_fetch, url="https://example.com")
    assert out.startswith("ERROR") and "web_search" in out
