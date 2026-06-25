"""Tests for the Model/Deployment layer (registry v2)."""
from visvoai.ai import deployments as d
from visvoai.ai.deployments import DeploymentInfo, ThinkingMechanism
from visvoai.ai.model_registry import Capability


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
    assert info.thinking_default == "medium"   # from default_thinking_label "Think"


def test_thinking_mechanism_derivation():
    assert d.get_deployment("gemini:gemini-3-flash-preview").thinking is ThinkingMechanism.GEMINI_LEVEL
    assert d.get_deployment("gemini:gemini-2.5-flash").thinking is ThinkingMechanism.GEMINI_BUDGET
    # a non-reasoning model → NONE
    assert d.get_deployment("together:llama-3.3-70b").thinking is ThinkingMechanism.NONE


def test_list_deployments_filters_and_default():
    chat = d.list_deployments(Capability.CHAT)
    assert chat and all(Capability.CHAT in c.capabilities for c in chat)
    assert all(isinstance(c, DeploymentInfo) for c in chat)
    # default chat deployment is the registry default model's deployment
    assert d.default_deployment(Capability.CHAT) == "gemini:gemini-3-flash-preview"


def test_unknown_id_returns_none():
    assert d.get_deployment("nope:does-not-exist") is None
    assert d.get_deployment_info("nope:does-not-exist") is None
