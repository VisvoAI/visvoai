"""CLI catalog wiring: install + the picker filter (curated always, abundance per-key)."""
import pytest

from visvoai.ai import (
    BakedSource, Capability, DeploymentRegistry,
    get_default_registry, install_catalog, set_default_registry,
)
from visvoai.ai.model_registry import ModelDefinition
from visvoai.cli import agent


@pytest.fixture
def restore_registry():
    original = get_default_registry()
    yield
    set_default_registry(original)


def _extra(provider, api_id, key_env):
    """A models.dev-style entry for a NON-baked provider (carries its own key_env)."""
    return ModelDefinition(api_id=api_id, display_name=api_id, provider=provider,
                           input_cost_per_million=1.0, output_cost_per_million=2.0,
                           context_window=1000, capabilities=[Capability.CHAT],
                           base_url="https://x/v1", key_env=key_env)


def test_picker_shows_curated_always_and_keyed_abundance(restore_registry, monkeypatch):
    # install: baked floor + two extra providers (one we'll have a key for, one not)
    defs = BakedSource().models() + [
        _extra("acme", "acme/big", "ACME_API_KEY"),
        _extra("nokey", "nokey/m", "NOKEY_API_KEY"),
    ]
    install_catalog(defs)

    monkeypatch.setenv("ACME_API_KEY", "k")
    monkeypatch.delenv("NOKEY_API_KEY", raising=False)

    by_provider = {}
    for d in agent.chat_deployments():
        by_provider.setdefault(d.provider, 0)
        by_provider[d.provider] += 1

    # keyed non-baked provider → shown (abundance)
    assert by_provider.get("acme") == 1
    # unkeyed non-baked provider → hidden entirely
    assert "nokey" not in by_provider
    # curated baked providers → always present (gemini is the baked default)
    assert by_provider.get("gemini", 0) >= 1


def test_baked_deployment_ids_are_from_baked_floor():
    ids = agent._baked_deployment_ids()
    baked = {info.id for info in DeploymentRegistry(BakedSource().models()).list_deployments(Capability.CHAT)}
    assert ids == baked and ids  # non-empty, exactly the baked floor
