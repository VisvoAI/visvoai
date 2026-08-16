"""Tests for the Model/Deployment layer (registry v2)."""
from visvoai.ai import deployments as d
from visvoai.ai.deployments import DeploymentInfo
from visvoai.ai.thinking import ThinkingLevel, ThinkingMechanism
from visvoai.ai.model_registry import MODELS, Capability


def test_same_model_multiple_providers_merges():
    # Llama 3.3 70B is one Model with two Deployments (Together + OpenRouter)
    deps = d.deployments_for("llama-3.3-70b")
    ids = sorted(x.id() for x in deps)
    assert ids == ["openrouter:llama-3.3-70b", "together:llama-3.3-70b"]
    # distinct provider slugs, shared model
    slugs = {x.provider: x.slug for x in deps}
    assert slugs["together"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert slugs["openrouter"] == "meta-llama/llama-3.3-70b-instruct"


def test_resolve_composite_id_to_slug():
    dep = d.get_deployment("together:llama-3.3-70b")
    assert dep.model == "llama-3.3-70b"
    assert dep.slug == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert d.get_deployment("openrouter:llama-3.3-70b").slug == "meta-llama/llama-3.3-70b-instruct"


def test_deployment_info_is_a_safe_projection():
    info = d.get_deployment_info("gemini:gemini-3-flash-preview")
    assert isinstance(info, DeploymentInfo)
    # public projection must NOT expose slug or the thinking mechanism
    assert not hasattr(info, "slug")
    assert not hasattr(info, "thinking")
    assert info.reasoning is True
    # the consumer renders thinking_levels + preselects default_thinking
    assert info.supports_thinking is True
    assert info.thinking_levels == [ThinkingLevel.OFF, ThinkingLevel.LOW,
                                    ThinkingLevel.MEDIUM, ThinkingLevel.HIGH]
    assert info.default_thinking is ThinkingLevel.MEDIUM   # from default_thinking_label "Think"


def test_non_reasoning_deployment_has_no_levels():
    info = d.get_deployment_info("together:llama-3.3-70b")
    assert info.supports_thinking is False
    assert info.thinking_levels == []
    assert info.default_thinking is ThinkingLevel.OFF


def test_thinking_mechanism_derivation():
    assert d.get_deployment("gemini:gemini-3-flash-preview").thinking is ThinkingMechanism.GEMINI_LEVEL
    assert d.get_deployment("gemini:gemini-2.5-flash").thinking is ThinkingMechanism.GEMINI_BUDGET
    # a non-reasoning model → NONE
    assert d.get_deployment("together:llama-3.3-70b").thinking is ThinkingMechanism.NONE


def test_list_deployments_filters_and_default():
    chat = d.list_deployments(Capability.CHAT)
    assert chat and all(Capability.CHAT in c.capabilities for c in chat)
    assert all(isinstance(c, DeploymentInfo) for c in chat)
    # The default chat deployment is the registry's default=True model — asserted
    # against the registry rather than a literal id, so changing which model is
    # default does not break this test. What is under test is the resolution
    # rule, not today's pick.
    default_model = next(m for m in MODELS if m.default)
    assert d.default_deployment(Capability.CHAT) == f"{default_model.provider}:{default_model.api_id}"


def test_unknown_id_returns_none():
    assert d.get_deployment("nope:does-not-exist") is None
    assert d.get_deployment_info("nope:does-not-exist") is None


# ── consumer-set defaults ─────────────────────────────────────────────────────

def _clear_overrides():
    for cap in list(d.get_default_overrides()):
        d.set_default_deployment(cap, None)


def test_override_beats_the_package_default():
    _clear_overrides()
    baseline = d.default_deployment(Capability.CHAT)
    other = next(c.id for c in d.list_deployments(Capability.CHAT) if c.id != baseline)
    try:
        d.set_default_deployment(Capability.CHAT, other)
        assert d.default_deployment(Capability.CHAT) == other
    finally:
        _clear_overrides()
    # clearing restores the package's own answer
    assert d.default_deployment(Capability.CHAT) == baseline


def test_override_is_validated_when_set_not_when_used():
    _clear_overrides()
    # unknown id
    try:
        d.set_default_deployment(Capability.CHAT, "nope:does-not-exist")
        assert False, "expected ValueError for an unknown deployment id"
    except ValueError as e:
        assert "unknown deployment id" in str(e)
    # a real deployment that does not declare the capability
    non_search = next(
        (c.id for c in d.list_deployments(Capability.CHAT)
         if Capability.SEARCH not in c.capabilities), None)
    if non_search:
        try:
            d.set_default_deployment(Capability.SEARCH, non_search)
            assert False, "expected ValueError for a missing capability"
        except ValueError as e:
            assert "does not declare" in str(e)
    assert d.get_default_overrides() == {}


def test_provider_filter_ignores_a_foreign_override():
    """Asking for the default Anthropic chat model must not return a Gemini one
    just because a consumer set that globally."""
    _clear_overrides()
    gemini = next((c.id for c in d.list_deployments(Capability.CHAT)
                   if c.provider == "gemini"), None)
    other_provider = next((c.provider for c in d.list_deployments(Capability.CHAT)
                           if c.provider != "gemini"), None)
    if not (gemini and other_provider):
        return
    try:
        d.set_default_deployment(Capability.CHAT, gemini)
        scoped = d.default_deployment(Capability.CHAT, provider=other_provider)
        assert scoped != gemini
        assert scoped is None or scoped.startswith(f"{other_provider}:")
    finally:
        _clear_overrides()
