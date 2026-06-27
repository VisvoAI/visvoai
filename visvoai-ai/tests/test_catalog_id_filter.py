"""build_catalog drops models whose id can't round-trip through the codec
(e.g. cloudflare's '@cf/…' slugs that collide with the '@effort' marker)."""
from visvoai.ai.catalog.engine import CatalogSource, build_catalog
from visvoai.ai.model_registry import Capability, ModelDefinition


def _md(provider, api_id):
    return ModelDefinition(
        api_id=api_id, display_name=api_id, provider=provider,
        input_cost_per_million=0.0, output_cost_per_million=0.0,
        capabilities=[Capability.CHAT],
    )


class _Src(CatalogSource):
    def __init__(self, mds):
        self._mds = mds

    def models(self):
        return self._mds


def test_drops_at_prefixed_slug():
    good = _md("openrouter", "x-ai/grok-3")
    bad = _md("cloudflare-workers-ai", "@cf/ibm-granite/granite-4.0-h-micro")
    out = build_catalog([_Src([good, bad])])
    ids = {(m.provider, m.api_id) for m in out}
    assert ("openrouter", "x-ai/grok-3") in ids
    assert ("cloudflare-workers-ai", "@cf/ibm-granite/granite-4.0-h-micro") not in ids


def test_keeps_normal_slugs():
    mds = [_md("together", "deepseek-ai/DeepSeek-V3"), _md("groq", "llama-3.3-70b")]
    out = build_catalog([_Src(mds)])
    assert len(out) == 2
