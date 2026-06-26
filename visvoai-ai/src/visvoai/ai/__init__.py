"""
visvoai.ai — Unified multi-provider LLM access.

Deployment-keyed: a Model can be served by many providers; the callable/billable
unit is a Deployment, identified by a composite id ("together:llama-3.3-70b").

Quick start:
    from visvoai.ai import build_chat_model, list_deployments, ThinkingLevel
    model = build_chat_model("gemini:gemini-3-flash-preview", level="medium")
    # provider key from the matching env var; pass api_key= to override
"""
from visvoai.ai.model_registry import ModelDefinition, Capability, get_model
from visvoai.ai.identity import IdentityCodec, ColonAtCodec, DeploymentId, DEFAULT_CODEC
from visvoai.ai.thinking import ThinkingLevel, ThinkingMechanism, thinking_kwargs, resolve_level
from visvoai.ai.deployments import (
    Model, Deployment, DeploymentInfo, DeploymentRegistry,
    get_deployment, get_deployment_info, deployments_for, list_deployments,
    default_deployment, install_catalog, set_default_registry, get_default_registry,
)
from visvoai.ai.catalog import CatalogSource, BakedSource, build_catalog
from visvoai.ai.resolve import build_chat_model, cost_of
from visvoai.ai.search import FetchError, SearchResult, SearchSource, fetch_url, run_search
from visvoai.ai.usage import usage_from
from visvoai.ai.providers.base import Provider, NotSupported, default_content_events
from visvoai.ai.providers.config import resolve_api_key
from visvoai.ai.providers.gemini import GeminiProvider
from visvoai.ai.providers.anthropic import AnthropicProvider
from visvoai.ai.providers.openai_compat import OpenAICompatProvider, ReasoningChatOpenAI
from visvoai.ai.providers.factory import get_provider, get_provider_for_model

__all__ = [
    # primary entry points
    "build_chat_model", "cost_of", "usage_from", "run_search", "fetch_url",
    "SearchResult", "SearchSource", "FetchError",
    "list_deployments", "get_deployment_info", "default_deployment", "deployments_for",
    # catalog engine + dynamic-catalog seam
    "CatalogSource", "BakedSource", "build_catalog",
    "DeploymentRegistry", "install_catalog", "set_default_registry", "get_default_registry",
    # thinking (public)
    "ThinkingLevel",
    # identity
    "IdentityCodec", "ColonAtCodec", "DeploymentId", "DEFAULT_CODEC",
    # types
    "DeploymentInfo", "Capability",
    # providers + facades
    "Provider", "NotSupported", "default_content_events", "resolve_api_key",
    "GeminiProvider", "AnthropicProvider", "OpenAICompatProvider", "ReasoningChatOpenAI",
    "get_provider", "get_provider_for_model",
    # internal-ish (kept exported for now; consumers should prefer DeploymentInfo)
    "Model", "Deployment", "ThinkingMechanism", "thinking_kwargs", "resolve_level",
    "get_deployment", "get_model", "ModelDefinition",
]
