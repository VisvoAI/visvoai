"""Tests for RemoteModelsDevSource: fresh-cache / fetch / stale-fallback / none, no network."""
import json
import os
import time

from visvoai.ai.catalog.sources.remote import RemoteModelsDevSource

# Minimal valid catalog the adapter can map (one callable provider, one text model).
CATALOG = {
    "deepseek": {
        "npm": "@ai-sdk/openai-compatible", "api": "https://api.deepseek.com",
        "env": ["DEEPSEEK_API_KEY"],
        "models": {"deepseek-chat": {
            "id": "deepseek-chat", "name": "DeepSeek", "tool_call": True, "reasoning": False,
            "modalities": {"input": ["text"], "output": ["text"]},
            "limit": {"context": 1000}, "cost": {"input": 0.1, "output": 0.2},
        }},
    }
}


def _boom():
    raise RuntimeError("network down")


def test_fresh_cache_is_used_without_fetching(tmp_path):
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps(CATALOG))
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return {}

    src = RemoteModelsDevSource(cache, ttl_seconds=10_000, fetcher=fetcher)
    ids = {m.api_id for m in src.models()}
    assert ids == {"deepseek-chat"}
    assert calls["n"] == 0  # fresh cache → no network


def test_stale_cache_triggers_fetch_and_rewrites(tmp_path):
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps({}))            # empty/old
    os.utime(cache, (time.time() - 99_999, time.time() - 99_999))  # make it stale

    src = RemoteModelsDevSource(cache, ttl_seconds=10, fetcher=lambda: CATALOG)
    ids = {m.api_id for m in src.models()}
    assert ids == {"deepseek-chat"}
    assert json.loads(cache.read_text()) == CATALOG  # cache rewritten


def test_fetch_failure_falls_back_to_stale_cache(tmp_path):
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps(CATALOG))
    os.utime(cache, (time.time() - 99_999, time.time() - 99_999))  # stale → wants refresh

    src = RemoteModelsDevSource(cache, ttl_seconds=10, fetcher=_boom)
    ids = {m.api_id for m in src.models()}
    assert ids == {"deepseek-chat"}  # served stale cache despite fetch failure


def test_no_cache_and_fetch_fails_yields_empty(tmp_path):
    cache = tmp_path / "missing.json"  # does not exist
    # bundled fallback off → empty (engine would fall back to BakedSource). With it on,
    # the bundled snapshot is served instead — see test_offline_no_cache_falls_back_to_bundled_snapshot.
    src = RemoteModelsDevSource(cache, fetcher=_boom, use_bundled_fallback=False)
    assert src.models() == []


def test_first_run_no_cache_fetches_and_writes(tmp_path):
    cache = tmp_path / "sub" / "models.json"  # parent dir doesn't exist yet
    src = RemoteModelsDevSource(cache, fetcher=lambda: CATALOG)
    ids = {m.api_id for m in src.models()}
    assert ids == {"deepseek-chat"}
    assert cache.exists()


# ── A4: bundled snapshot offline floor ────────────────────────────────────────

def test_bundled_snapshot_loads_and_is_substantial():
    from visvoai.ai.catalog.sources.remote import load_bundled_snapshot
    snap = load_bundled_snapshot()
    assert snap is not None, "bundled modelsdev_snapshot.json.gz should ship in the package"
    # real models.dev has ~140 providers — sanity floor, not an exact count
    assert len(snap) > 50


def test_offline_no_cache_falls_back_to_bundled_snapshot(tmp_path):
    cache = tmp_path / "missing.json"  # no cache
    src = RemoteModelsDevSource(cache, fetcher=_boom)  # network down
    defs = src.models()
    # bundled snapshot yields the OpenAI-compat long tail, not empty
    assert len(defs) > 100


def test_bundled_fallback_can_be_disabled(tmp_path):
    cache = tmp_path / "missing.json"
    src = RemoteModelsDevSource(cache, fetcher=_boom, use_bundled_fallback=False)
    assert src.models() == []  # opted out → empty, engine falls to BakedSource
