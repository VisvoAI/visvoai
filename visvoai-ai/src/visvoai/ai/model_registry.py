"""
model_registry.py

Single source of truth for all LLM models: identity, pricing, and capabilities.

UI-facing model options (the ModelOption picker layer) are NOT here — they live in the
platform at backend/llm/model_registry.py. This package exposes only the model facts.

Pricing source: https://ai.google.dev/gemini-api/docs/pricing (Gemini Developer API)
Last verified: May 2026

KEY BILLING RULES FOR GEMINI API (not Vertex AI — prices differ):
─────────────────────────────────────────────────────────────────
1. CACHED TOKENS are a SUBSET of prompt_token_count.
   Bill non-cached input:  (prompt_token_count - cached_content_token_count) * input_rate
   Bill cached input:      cached_content_token_count * cache_read_cost_per_million

2. THINKING TOKENS (thoughts_token_count) are billed at the SAME rate as
   regular output tokens (candidates_token_count). No separate thinking rate.
   Total billable output = candidates_token_count + thoughts_token_count.

3. GOOGLE SEARCH GROUNDING — two billing models by model generation:

   Gemini 2.5 and older:
   - Billed per GROUNDED API REQUEST (one charge per API call that uses grounding).
   - Rate: $35 / 1,000 grounded prompts = $0.035 per API call.
   - Free tier: 1,500 RPD free (shared between Flash and Flash-Lite).
   - search_billed_per_request = True

   Gemini 3+ models:
   - Billed per INDIVIDUAL SEARCH QUERY (one API call can fire multiple sub-queries).
   - Rate: $14 / 1,000 search queries = $0.014 per sub-query.
   - Free tier: 5,000 prompts/month FREE (shared across ALL Gemini 3 models).
   - search_billed_per_request = False

Prices are in USD per 1,000,000 tokens unless noted.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class Capability(str, Enum):
    """What a model can be used for. A model declares one or more; consumers resolve a model
    that has the capability they need, and the facade validates it before invoking the matching
    method (CHAT → build_chat_model/generate, SEARCH → search, …). Routing/validation only —
    NOT a pricing axis (pricing lives in the flat rate-card fields below)."""
    CHAT = "chat"                  # agent loop + utility text generate()
    SEARCH = "search"              # grounded web search() (Google Search grounding — Gemini)
    DEEP_RESEARCH = "deep_research"  # background/async research interactions (Gemini)
    IMAGE_GEN = "image_gen"        # image generation (Imagen)
    AUDIO_GEN = "audio_gen"        # text-to-speech audio generation
    EMBEDDING = "embedding"        # text/multimodal embeddings
    # NOTE: IMAGE_GEN/AUDIO_GEN/EMBEDDING models are DEFINED here (registry = full inventory) but
    # their tools still call the SDK directly — routing them through facade capability methods +
    # cost-tracking is the deferred modality pass.


@dataclass
class ModelDefinition:
    api_id: str                              # exact string sent to the API
    display_name: str                        # shown in UI
    input_cost_per_million: float
    output_cost_per_million: float
    cache_read_cost_per_million: float = 0.0
    search_query_cost: float = 0.0
    search_billed_per_request: bool = False
    provider: str = "gemini"                 # "gemini" | "anthropic" | "openai" | "together" — must equal the api_keys key name
    icon_url: str = "https://www.google.com/favicon.ico"
    supports_thinking: bool = False
    enabled: bool = True                     # controls UI visibility
    deprecated: bool = False                 # excluded from UI and cost lookups
    default: bool = False                    # exactly one model should be True
    default_thinking_label: Optional[str] = None  # which thinking variant is the default (None = base)
    capabilities: List[Capability] = field(default_factory=lambda: [Capability.CHAT])
    # For models NOT billed per-token (e.g. image gen, billed per image). Token-priced models
    # (chat, TTS, embedding) leave these None and use input/output_cost_per_million. Approximate
    # by design — see module docstring; the provider's own billing is authoritative.
    unit_cost: Optional[float] = None        # cost per `unit` in USD
    unit: Optional[str] = None               # e.g. "per_image"


# =============================================================================
# Model Registry
# =============================================================================

MODELS: List[ModelDefinition] = [

    # -------------------------------------------------------------------------
    # Gemini 3.5
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="gemini-3.5-flash",
        display_name="Gemini 3.5 Flash",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=1.50,
        output_cost_per_million=9.00,
        cache_read_cost_per_million=0.375,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=True,
        enabled=True,
    ),

    # -------------------------------------------------------------------------
    # Gemini 3.1
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=2.00,
        output_cost_per_million=12.00,
        cache_read_cost_per_million=0.50,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=True,
        enabled=True,
    ),
    # Internal variant used by tools — not exposed in UI
    ModelDefinition(
        api_id="gemini-3.1-pro-preview-customtools",
        display_name="Gemini 3.1 Pro (Custom Tools)",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=2.00,
        output_cost_per_million=12.00,
        cache_read_cost_per_million=0.50,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=True,
        enabled=False,
    ),
    ModelDefinition(
        api_id="gemini-3.1-flash-lite",
        display_name="Gemini 3.1 Flash Lite",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=0.25,
        output_cost_per_million=1.50,
        cache_read_cost_per_million=0.0625,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=False,
        enabled=True,
    ),
    # Live/real-time model — not for standard chat
    ModelDefinition(
        api_id="gemini-3.1-flash-live-preview",
        display_name="Gemini 3.1 Flash Live",
        input_cost_per_million=0.75,
        output_cost_per_million=4.50,
        cache_read_cost_per_million=0.0,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=False,
        enabled=False,
    ),

    # -------------------------------------------------------------------------
    # Gemini 3
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="gemini-3-flash-preview",
        display_name="Gemini 3 Flash",
        capabilities=[Capability.CHAT, Capability.SEARCH, Capability.DEEP_RESEARCH],
        input_cost_per_million=0.50,
        output_cost_per_million=3.00,
        cache_read_cost_per_million=0.125,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=True,
        enabled=True,
        default=True,
        default_thinking_label="Think",
    ),
    ModelDefinition(
        api_id="gemini-3-pro-image",
        display_name="Gemini 3 Pro Image",
        input_cost_per_million=2.00,
        output_cost_per_million=120.00,
        cache_read_cost_per_million=0.50,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=False,
        enabled=False,
    ),
    # Old ID for gemini-3-pro-image — kept for cost tracking of historical calls
    ModelDefinition(
        api_id="gemini-3-pro-image-preview",
        display_name="Gemini 3 Pro Image (Preview)",
        input_cost_per_million=2.00,
        output_cost_per_million=12.00,
        cache_read_cost_per_million=0.50,
        search_query_cost=0.014,
        search_billed_per_request=False,
        supports_thinking=False,
        enabled=False,
        deprecated=True,
    ),

    # -------------------------------------------------------------------------
    # Gemini 2.5
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=1.25,
        output_cost_per_million=10.00,
        cache_read_cost_per_million=0.3125,
        search_query_cost=0.035,
        search_billed_per_request=True,
        supports_thinking=True,
        enabled=True,
    ),
    ModelDefinition(
        api_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=0.30,
        output_cost_per_million=2.50,
        cache_read_cost_per_million=0.075,
        search_query_cost=0.035,
        search_billed_per_request=True,
        supports_thinking=True,
        enabled=True,
    ),
    # Old preview alias — kept for cost tracking of historical calls
    ModelDefinition(
        api_id="gemini-2.5-flash-preview",
        display_name="Gemini 2.5 Flash (Preview)",
        input_cost_per_million=0.30,
        output_cost_per_million=2.50,
        cache_read_cost_per_million=0.075,
        search_query_cost=0.035,
        search_billed_per_request=True,
        supports_thinking=True,
        enabled=False,
        deprecated=True,
    ),
    ModelDefinition(
        api_id="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash Lite",
        capabilities=[Capability.CHAT, Capability.SEARCH],
        input_cost_per_million=0.10,
        output_cost_per_million=0.40,
        cache_read_cost_per_million=0.025,
        search_query_cost=0.035,
        search_billed_per_request=True,
        supports_thinking=False,
        enabled=True,
    ),
    # Old preview alias — kept for cost tracking of historical calls
    ModelDefinition(
        api_id="gemini-2.5-flash-lite-preview-09-2025",
        display_name="Gemini 2.5 Flash Lite (Preview)",
        input_cost_per_million=0.10,
        output_cost_per_million=0.40,
        cache_read_cost_per_million=0.025,
        search_query_cost=0.035,
        search_billed_per_request=True,
        supports_thinking=False,
        enabled=False,
        deprecated=True,
    ),

    # -------------------------------------------------------------------------
    # Tool / capability models (non-chat). Defined for inventory + cost lookup;
    # enabled=False keeps them out of the chat model picker. Their tools still call
    # the SDK directly (deferred modality pass). Pricing verified 2026-06-20.
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="imagen-4.0-fast-generate-001",
        display_name="Imagen 4 Fast",
        capabilities=[Capability.IMAGE_GEN],
        input_cost_per_million=0.0,          # not token-billed
        output_cost_per_million=0.0,
        unit_cost=0.02,                      # $0.02 / image
        unit="per_image",
        enabled=False,
    ),
    ModelDefinition(
        api_id="gemini-2.5-flash-preview-tts",
        display_name="Gemini 2.5 Flash TTS",
        capabilities=[Capability.AUDIO_GEN],
        input_cost_per_million=0.50,         # text input
        output_cost_per_million=10.00,       # audio output tokens
        enabled=False,
    ),
    ModelDefinition(
        api_id="gemini-embedding-2",
        display_name="Gemini Embedding 2",
        capabilities=[Capability.EMBEDDING],
        input_cost_per_million=0.20,         # per 1M input tokens; no output
        output_cost_per_million=0.0,
        enabled=False,
    ),

    # -------------------------------------------------------------------------
    # Anthropic Claude
    # -------------------------------------------------------------------------
    # NOTE: thinking is OFF for all Claude models — the Anthropic engine only emits the
    # legacy {"type":"enabled","budget_tokens":N} thinking API, which 400s on 4.6+ models.
    # Do NOT set supports_thinking=True here until anthropic.py emits adaptive thinking.
    ModelDefinition(
        api_id="claude-fable-5",
        display_name="Claude Fable 5",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=10.00,
        output_cost_per_million=50.00,
        enabled=False,  # premium tier ($10/$50) — registered for cost tracking, off in the picker
    ),
    ModelDefinition(
        api_id="claude-opus-4-8",
        display_name="Claude Opus 4.8",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=5.00,
        output_cost_per_million=25.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=1.00,
        output_cost_per_million=5.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        enabled=False,
        deprecated=True,
    ),
    ModelDefinition(
        api_id="claude-3-5-haiku-20241022",
        display_name="Claude Haiku 3.5",
        provider="anthropic",
        icon_url="https://www.anthropic.com/favicon.ico",
        input_cost_per_million=0.80,
        output_cost_per_million=4.00,
        enabled=False,
        deprecated=True,
    ),

    # -------------------------------------------------------------------------
    # OpenAI — OpenAI-compatible path (ChatOpenAI, no base_url override). provider="openai"
    # matches the config.providers.openai block + the api_keys "openai" key.
    # Pricing is the approximate rate card (USD/1M tokens) — provider billing is authoritative.
    # Only NON-reasoning chat models are enabled: ChatOpenAI sends `temperature`, and the
    # reasoning models (gpt-5 / o-series) 400 on any temperature != 1. Enabling those needs
    # the temperature drop + reasoning_effort mapping first — see the disabled block below.
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="gpt-4.1",
        display_name="GPT-4.1",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=2.00,
        output_cost_per_million=8.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="gpt-4.1-mini",
        display_name="GPT-4.1 mini",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=0.40,
        output_cost_per_million=1.60,
        enabled=True,
    ),
    ModelDefinition(
        api_id="gpt-4o",
        display_name="GPT-4o",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=2.50,
        output_cost_per_million=10.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        enabled=True,
    ),
    # --- Reasoning models -----------------------------------------------------
    # supports_thinking=True marks them as reasoning models. The OpenAI compat path
    # reacts: omits temperature (these reject temperature != 1) and sends
    # max_completion_tokens instead of max_tokens. reasoning_effort runs at default.
    ModelDefinition(
        api_id="gpt-5",
        display_name="GPT-5",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=1.25,
        output_cost_per_million=10.00,
        supports_thinking=True,
        enabled=True,
    ),
    ModelDefinition(
        api_id="o4-mini",
        display_name="o4 Mini",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=1.10,
        output_cost_per_million=4.40,
        supports_thinking=True,
        enabled=True,
    ),
    ModelDefinition(
        api_id="o3",
        display_name="o3",
        provider="openai",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=2.00,
        output_cost_per_million=8.00,
        supports_thinking=True,
        enabled=True,
    ),

    # -------------------------------------------------------------------------
    # Together.ai — OpenAI-compatible (ChatOpenAI + base_url). provider="together"
    # must match the config.providers.together block (key ref + base_url). Top-10
    # function-calling-capable flagships (the agent loop needs tool use), exact api_ids
    # + pricing pulled from the LIVE /v1/models catalog (scripts/together_models.py,
    # 2026-06-19). No native thinking → base ModelOption only.
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="deepseek-ai/DeepSeek-V4-Pro",
        display_name="DeepSeek V4 Pro",
        provider="together",
        icon_url="https://www.deepseek.com/favicon.ico",
        input_cost_per_million=1.74,
        output_cost_per_million=3.48,
        enabled=True,
    ),
    ModelDefinition(
        api_id="Qwen/Qwen3-235B-A22B-Instruct-2507-tput",
        display_name="Qwen3 235B",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=qwen.ai",
        input_cost_per_million=0.20,
        output_cost_per_million=0.60,
        enabled=True,
    ),
    ModelDefinition(
        api_id="moonshotai/Kimi-K2.6",
        display_name="Kimi K2.6",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=moonshot.ai",
        input_cost_per_million=1.20,
        output_cost_per_million=4.50,
        enabled=True,
    ),
    ModelDefinition(
        api_id="moonshotai/Kimi-K2.7-Code",
        display_name="Kimi K2.7 Code",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=moonshot.ai",
        input_cost_per_million=0.95,
        output_cost_per_million=4.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="zai-org/GLM-5.2",
        display_name="GLM-5.2",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=z.ai",
        input_cost_per_million=1.40,
        output_cost_per_million=4.40,
        enabled=True,
    ),
    ModelDefinition(
        api_id="zai-org/GLM-5.1",
        display_name="GLM-5.1",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=z.ai",
        input_cost_per_million=1.40,
        output_cost_per_million=4.40,
        enabled=True,
    ),
    ModelDefinition(
        api_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        display_name="Llama 3.3 70B",
        provider="together",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=llama.com",
        input_cost_per_million=1.04,
        output_cost_per_million=1.04,
        enabled=True,
    ),
    ModelDefinition(
        api_id="openai/gpt-oss-120b",
        display_name="GPT-OSS 120B",
        provider="together",
        icon_url="https://openai.com/favicon.ico",
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        enabled=True,
    ),
    ModelDefinition(
        api_id="nvidia/nemotron-3-ultra-550b-a55b",
        display_name="Nemotron 3 Ultra 550B",
        provider="together",
        icon_url="https://www.nvidia.com/favicon.ico",
        input_cost_per_million=0.60,
        output_cost_per_million=3.60,
        enabled=True,
    ),
    ModelDefinition(
        api_id="MiniMaxAI/MiniMax-M3",
        display_name="MiniMax M3",
        provider="together",
        icon_url="https://www.minimax.io/favicon.ico",
        input_cost_per_million=0.30,
        output_cost_per_million=1.20,
        enabled=True,
    ),
    # (Mistral dropped — no serverless-available Mistral model on Together as of 2026-06-20;
    #  Ministral/Mistral-Small/Mixtral all require dedicated endpoints → would 400.)
    # (Gemma 4 31B dropped 2026-06-20 — serverless-listed but consistently flaky
    #  (repeated timeouts / connection errors); with no fallback chain it would error outright.)

    # -------------------------------------------------------------------------
    # OpenRouter — OpenAI-compatible aggregator (ChatOpenAI + base_url). provider="openrouter"
    # must match the config.providers.openrouter block. api_ids are OpenRouter's namespaced
    # slugs (provider/model). Curated starter set: distinctive, function-calling-capable models
    # not otherwise wired here. IDs + pricing are APPROXIMATE — refresh against the live catalog
    # (GET https://openrouter.ai/api/v1/models) before relying on them; provider billing is
    # authoritative. Non-reasoning models only (the OpenAI temperature/max_completion_tokens
    # special-casing in OpenAICompatProvider is gated to provider=="openai", not openrouter).
    # -------------------------------------------------------------------------
    ModelDefinition(
        api_id="x-ai/grok-3",
        display_name="Grok 3",
        provider="openrouter",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=x.ai",
        input_cost_per_million=3.00,
        output_cost_per_million=15.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="mistralai/mistral-large",
        display_name="Mistral Large",
        provider="openrouter",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=mistral.ai",
        input_cost_per_million=2.00,
        output_cost_per_million=6.00,
        enabled=True,
    ),
    ModelDefinition(
        api_id="meta-llama/llama-3.3-70b-instruct",
        display_name="Llama 3.3 70B (OpenRouter)",
        provider="openrouter",
        icon_url="https://www.google.com/s2/favicons?sz=64&domain=llama.com",
        input_cost_per_million=0.13,
        output_cost_per_million=0.40,
        enabled=True,
    ),
]


# =============================================================================
# Derived lookups
# =============================================================================

# Keyed by api_id — used for cost tracking (same shape as the old MODEL_PRICING_MAP)
MODEL_PRICING_MAP: Dict[str, Dict[str, Any]] = {
    m.api_id: {
        "input_cost_per_million_tokens": m.input_cost_per_million,
        "output_cost_per_million_tokens": m.output_cost_per_million,
        "cache_read_cost_per_million_tokens": m.cache_read_cost_per_million,
        "search_query_cost": m.search_query_cost,
        "search_billed_per_request": m.search_billed_per_request,
        "unit_cost": m.unit_cost,
        "unit": m.unit,
    }
    for m in MODELS
}

# Quick lookup by api_id
_MODEL_BY_API_ID: Dict[str, ModelDefinition] = {m.api_id: m for m in MODELS}


def get_model(api_id: str) -> Optional[ModelDefinition]:
    return _MODEL_BY_API_ID.get(api_id)


# Default model per capability, used when a caller needs a capability but doesn't pin a model
# (e.g. the search tool needs "a SEARCH model"). Module-level for now; a future user-settings
# layer can override this per user — keeping it OFF ModelDefinition is what makes that swap clean.
DEFAULT_MODEL_FOR: Dict[Capability, str] = {
    Capability.SEARCH: "gemini-3-flash-preview",
    Capability.DEEP_RESEARCH: "gemini-3-flash-preview",
}


def default_model_for(capability: Capability) -> str:
    """The default model id for a capability. Raises if none is configured."""
    model_id = DEFAULT_MODEL_FOR.get(capability)
    if model_id is None:
        raise ValueError(f"No default model configured for capability {capability.value}")
    return model_id


# Crash at startup if the registry is misconfigured
_default_models = [m for m in MODELS if m.default]
if len(_default_models) == 0:
    raise RuntimeError("model_registry: no model is marked default=True — exactly one must be.")
if len(_default_models) > 1:
    raise RuntimeError(
        f"model_registry: multiple models marked default=True: "
        f"{[m.api_id for m in _default_models]} — exactly one must be."
    )

# Every DEFAULT_MODEL_FOR target must be a registered model that actually declares the
# capability — fail at import, not at call time (this is what catches a stale default).
for _cap, _mid in DEFAULT_MODEL_FOR.items():
    _md = _MODEL_BY_API_ID.get(_mid)
    if _md is None:
        raise RuntimeError(f"model_registry: DEFAULT_MODEL_FOR[{_cap.value}] = '{_mid}' is not in the registry.")
    if _cap not in _md.capabilities:
        raise RuntimeError(
            f"model_registry: DEFAULT_MODEL_FOR[{_cap.value}] = '{_mid}' does not declare capability {_cap.value} "
            f"(has {[c.value for c in _md.capabilities]})."
        )


def resolve_gemini_thinking_kwargs(model_api_id: str, thinking_level: Optional[str]) -> Dict[str, Any]:
    """Translate the UI-facing thinking_level string into the correct ChatGoogleGenerativeAI kwargs.

    Gemini 3+ → thinking_level string ('minimal'|'low'|'medium'|'high')
    Gemini 2.x → thinking_budget int (0 = off, >0 = enabled with that token budget)

    The UI only exposes Think / Think Hard labels — this function hides the per-family API difference.
    """
    # Gemini 2.x family — detected by major version prefix
    is_gemini2 = any(model_api_id.startswith(p) for p in ("gemini-2.", "gemini-2-"))

    if is_gemini2:
        budget_map = {"minimal": 0, "none": 0, "low": 1024, "medium": 4096, "high": 8192}
        budget = budget_map.get(thinking_level or "minimal", 0)
        return {
            "thinking_budget": budget,
            "include_thoughts": budget > 0,
        }
    else:
        # Gemini 3+ — thinking_level string enum
        level = thinking_level or "minimal"
        return {
            "thinking_level": level,
            "include_thoughts": level != "minimal",
        }
