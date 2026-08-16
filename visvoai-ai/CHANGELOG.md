# Changelog — visvoai-ai

All notable changes to this package. Versions follow `v0.MINOR.PATCH` while the API is
unstable (pre-1.0): MINOR for new capability or breaking changes, PATCH for fixes. No
major (1.0) bump until the surface stabilizes.

## [0.2.4] — 2026-08

### Added
- `gemini-3.7-flash` and `gemini-3.6-flash` to the model registry. Both carry a
  1,048,576-token context, tool calling and thinking, and are registered for
  `CHAT` and `SEARCH`.

  Context window, input and output rates come from models.dev rather than being
  typed by hand, since a wrong `input_cost_per_million` silently corrupts every
  cost figure derived from it:

  | model | input | output | cache read |
  |---|---|---|---|
  | `gemini-3.7-flash` | $0.75 | $3.75 | $0.1875 |
  | `gemini-3.6-flash` | $1.50 | $7.50 | $0.375 |

  `cache_read_cost_per_million` deliberately does **not** follow models.dev.
  This registry prices cache reads at 25% of input, per the Gemini Developer API
  pricing page named in the module docstring; models.dev reports 10%. That gap
  is uniform — exactly 2.5x across all seven existing Gemini entries — so it is
  a difference of convention, not a per-model error, and a new model following
  the other convention would have been the only inconsistent row in the table.

  `search_query_cost` is mirrored from `gemini-3.5-flash` — models.dev does not
  carry grounding pricing, and it is a provider-level rate rather than a
  per-model one.

  No default changed: `DEFAULT_MODEL_FOR` still points `SEARCH` and
  `DEEP_RESEARCH` at `gemini-3-flash-preview`.

## [0.2.3] — 2026-06

### Fixed
- Reasoning models on OpenAI-compatible providers (Together/OpenRouter/…) no longer
  hit the OpenAI **Responses API**. langchain-openai auto-switches to `/responses`
  when a top-level `reasoning` dict is present; those providers reject it
  (`400 Invalid Responses API request`) or return block-list content that breaks the
  next turn. `OPENROUTER_REASONING` now sends `reasoning` via `extra_body`, and
  `OpenAICompatProvider.build` pins `use_responses_api=False` for non-OpenAI providers.

## [0.2.2] — 2026-06

### Fixed
- `build_catalog` drops models whose id can't round-trip through the identity codec
  (e.g. cloudflare's `@cf/…` slugs, which collide with the `@effort` marker). They
  previously listed but crashed `get_deployment` — a landmine in any picker.

## [0.2.1] — 2026-06

### Fixed
- `resolve_api_key` now cleans keys (strips whitespace + a layer of wrapping quotes)
  at the single resolution chokepoint — covering explicit args, `env_var`, and the
  static map. A key with a trailing space/newline or wrapped in quotes (common from
  shells, `.env`, or config) was sent verbatim and silently rejected as `401 User not
  found`; it's now normalized before the request.

## [0.2.0] — 2026-06

### Added
- **Catalog engine** (`catalog/`): `CatalogSource` ABC, `BakedSource`, `build_catalog()`
  (merge → gate → validate). Output is `list[ModelDefinition]` — a drop-in for the static
  registry list.
- **models.dev adapter** (`catalog.sources.modelsdev`): `to_definitions()` / `ModelsDevSource`
  map the live models.dev catalog into `ModelDefinition`s. Admission is callability-based
  (derivable Chat Completions base_url + not bespoke/denied) — ~4150 defs / ~128 providers.
- **Remote source** (`catalog.sources.remote.RemoteModelsDevSource`): cached, offline-tolerant
  models.dev fetch (stdlib only). Degrades fresh-cache → fetch → stale-cache → bundled snapshot
  → empty; never raises.
- **Bundled snapshot**: `catalog/data/modelsdev_snapshot.json.gz` (generated, ~190 KB) as the
  OpenAI-compat offline floor, plus `scripts/generate_modelsdev_snapshot.py` (deterministic).
- **`DeploymentRegistry`**: instance-scoped Model/Deployment view; `install_catalog()` /
  `set_default_registry()` swap the module default — the dynamic-catalog seam.
- `ModelDefinition` / `Deployment` carry `base_url` + `key_env`; `build_chat_model` threads
  them so catalog-sourced (non-statically-wired) providers are self-contained.
- `ThinkingMechanism.ANTHROPIC_ADAPTIVE` for Claude 4.6+ (`{"type":"adaptive"}`); legacy
  `ANTHROPIC_BUDGET` retained for ≤4.5. `resolve_api_key(provider, env_var=…)`.

### Notes
- Registry `supports_thinking` stays `False` for Claude — the resolver dialect is correct but
  live-unverified against the Anthropic API.

## [0.1.0]
- Initial Model/Deployment registry, identity codec, per-provider thinking, provider facades.
