"""Tests for the catalog engine: sources → merge (later wins) → gate → validate."""
import pytest

from visvoai.ai.catalog import (
    BakedSource,
    CatalogSource,
    build_catalog,
    validate,
)
from visvoai.ai.model_registry import Capability, ModelDefinition


def _md(api_id="m", provider="together", inp=1.0, out=2.0, ctx=1000) -> ModelDefinition:
    return ModelDefinition(
        api_id=api_id, display_name=api_id, provider=provider,
        input_cost_per_million=inp, output_cost_per_million=out, context_window=ctx,
        capabilities=[Capability.CHAT],
    )


class _Src(CatalogSource):
    def __init__(self, models):
        self._m = models

    def models(self):
        return list(self._m)


def test_baked_source_defaults_to_registry():
    out = BakedSource().models()
    assert out and all(isinstance(m, ModelDefinition) for m in out)


def test_later_source_wins_wholesale():
    a = _Src([_md(api_id="x", inp=1.0)])
    b = _Src([_md(api_id="x", inp=9.0)])  # same (provider, api_id)
    out = build_catalog([a, b])
    xs = [m for m in out if m.api_id == "x"]
    assert len(xs) == 1 and xs[0].input_cost_per_million == 9.0


def test_new_keys_are_added_not_replaced():
    a = _Src([_md(api_id="x")])
    b = _Src([_md(api_id="y")])
    out = build_catalog([a, b])
    ids = {m.api_id for m in out}
    assert {"x", "y"} <= ids


def test_same_api_id_different_provider_are_distinct():
    a = _Src([_md(api_id="shared", provider="together")])
    b = _Src([_md(api_id="shared", provider="openrouter")])
    out = build_catalog([a, b])
    providers = {m.provider for m in out if m.api_id == "shared"}
    assert providers == {"together", "openrouter"}


def test_gate_drops_uncallable_and_keeps_rest():
    src = _Src([_md(api_id="keep", provider="together"),
                _md(api_id="drop", provider="alibaba-cn")])
    wired = {"together"}
    out = build_catalog([src], gate=lambda m: m.provider in wired)
    ids = {m.api_id for m in out}
    assert ids == {"keep"}


def test_validate_rejects_duplicate_key():
    with pytest.raises(ValueError, match="duplicate"):
        validate([_md(api_id="x"), _md(api_id="x")])


def test_validate_rejects_negative_cost():
    with pytest.raises(ValueError, match="negative cost"):
        validate([_md(api_id="x", inp=-1.0)])


# ── the install_catalog seam: catalog → default DeploymentRegistry ────────────

def test_registry_built_from_custom_defs_is_isolated():
    from visvoai.ai.deployments import DeploymentRegistry
    reg = DeploymentRegistry([_md(api_id="solo", provider="together")])
    assert reg.get_deployment("together:solo").slug == "solo"
    # an independent instance — does not touch the module default
    assert reg.get_deployment("gemini:gemini-3-flash-preview") is None


def test_install_catalog_swaps_default_then_restores():
    from visvoai.ai import deployments as d
    original = d.get_default_registry()
    try:
        d.install_catalog(build_catalog([BakedSource([_md(api_id="only", provider="together")])]))
        # free functions now reflect the installed catalog
        assert d.get_deployment("together:only") is not None
        assert d.get_deployment("gemini:gemini-3-flash-preview") is None
    finally:
        d.set_default_registry(original)
    # restored: the baked default is back
    assert d.get_deployment("gemini:gemini-3-flash-preview") is not None


# ── corrections ───────────────────────────────────────────────────────────────

def test_corrections_overlay_individual_fields():
    """A correction patches named fields and leaves the rest of the record alone —
    which is the whole point. Merge is 'later wins wholesale', so curation shipped
    as a source would clobber the live facts it is meant to sit on top of."""
    from visvoai.ai import BakedSource, build_catalog

    target = ("gemini", "gemini-3.5-flash")
    before = {(d.provider, d.api_id): d for d in build_catalog([BakedSource()])}[target]
    after = {(d.provider, d.api_id): d for d in build_catalog(
        [BakedSource()], corrections={target: {"search_query_cost": 0.99}})}[target]

    assert after.search_query_cost == 0.99
    assert after.input_cost_per_million == before.input_cost_per_million  # untouched


def test_correction_naming_an_unknown_field_raises():
    """A typo that silently did nothing would leave a correction that looks
    applied and is not."""
    from visvoai.ai import BakedSource, build_catalog
    import pytest

    with pytest.raises(ValueError, match="unknown field"):
        build_catalog([BakedSource()],
                      corrections={("gemini", "gemini-3.5-flash"): {"nope": 1}})


def test_correction_for_an_unknown_model_is_ignored():
    """Upstream dropping a model is stale, not fatal."""
    from visvoai.ai import BakedSource, build_catalog

    defs = build_catalog([BakedSource()],
                         corrections={("gemini", "ghost"): {"enabled": False}})
    assert defs  # no raise, catalog intact
