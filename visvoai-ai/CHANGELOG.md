# Changelog — visvoai-ai

All notable changes to this package. Versions follow `v0.MINOR.PATCH` while the API is
unstable (pre-1.0): MINOR for new capability or breaking changes, PATCH for fixes. No
major (1.0) bump until the surface stabilizes.

## [0.4.1] — 2026-08

### Fixed
- **`status` never reached `DeploymentInfo`.** 0.4.0 added it to
  `ModelDefinition` and to `Deployment` — the internal record — but not to the
  public read-only projection, which is *"the ONLY model-data type consumers
  touch"*. So the tag existed, the data flowed, and every consumer reading
  `info.status` got `AttributeError`. The feature was unusable as shipped.

  A regression test now asserts the field survives the hop to `DeploymentInfo`
  and is populated, not merely declared.

## [0.4.0] — 2026-08

Gemini facts now come from models.dev instead of being maintained by hand, and a
pricing error that hand-maintenance had been hiding is fixed.

### Fixed
- **Gemini `cache_read_cost_per_million` was 2.5x too high on all 14 models.**
  Google prices context-cache reads at **10% of input**
  (https://ai.google.dev/gemini-api/docs/pricing); this registry carried 25%.

  | model | was | now |
  |---|---|---|
  | `gemini-3.7-flash` | 0.1875 | **0.075** |
  | `gemini-3.5-flash` | 0.375 | **0.15** |
  | `gemini-2.5-pro` | 0.3125 | **0.125** |
  | …11 others | | |

  Reporting only — `estimated_cost_usd` was inflated wherever cached tokens were
  recorded; it never changed what a provider billed.

  This is a correction, not an update to new pricing. models.dev carried the
  same wrong figures and fixed them on 2026-04-20 — commit
  "[google] Fix cache_read cost in gemini-2.5-flash model" moved 0.075 → 0.03,
  and a sibling commit moved gemini-2.5-pro 0.31 → 0.125. Those pre-fix values
  are exactly what this registry still carried. Google did not change its
  pricing; a shared error was fixed upstream four months ago and not here.

  **Correcting the 0.2.4 notes:** they called the 25% figure a deliberate
  convention and used it to justify overriding models.dev, which had the correct
  10%. That was wrong. The gap was uniform across every Gemini row and
  uniformity was mistaken for intent. A regression test now asserts the 10%
  relationship, and the module docstring says to verify against the pricing page
  rather than against the rest of the file — internal consistency is what
  disguised this.

### Added
- **`build_catalog(..., corrections=...)`** — per-field overlays,
  `{(provider, api_id): {field: value}}`, applied after the merge. Deliberately
  not a `CatalogSource`: a source yields whole models and merge is "later wins
  wholesale", so curation shipped as a source would clobber the live facts it is
  meant to sit on. An unknown field raises (a typo that silently did nothing
  would look applied); an unknown model id is logged and ignored (upstream
  dropping a model is stale, not fatal).
- **`catalog.corrections.CURATED_CORRECTIONS`** — the handful of things
  models.dev does not model. Verified against its schema, not guessed: `Cost` is
  strictly per-token, so Google Search grounding (billed per query) has nowhere
  to live; there is no capability concept beyond `tool_call`/`reasoning`; and no
  thinking-default notion.
- **`ModelDefinition.status` / `DeploymentInfo.status`** — upstream lifecycle,
  `"alpha" | "beta" | None`. Presentation only: such models stay fully
  selectable, for consumers to surface as a tag. Retirement is `deprecated`, a
  separate axis.

### Changed
- **Gemini is sourced from models.dev.** `google` left the adapter's
  `BESPOKE_OR_DENY` set, where it sat beside Bedrock and Azure for a different
  reason — those are uncallable, Gemini was merely curated elsewhere. First-party
  providers now take a path that leaves `base_url`/`key_env` unset and lets the
  static provider config resolve them.

  35 Gemini models instead of 18. `gemini-3.6-flash` and `gemini-3.7-flash`
  would have arrived on their own; they were added by hand in 0.2.4, which is
  what prompted this.

  The baked source is not deleted — three models it carries are absent upstream
  (`gemini-2.5-flash-preview`, `gemini-2.5-flash-lite-preview-09-2025`,
  `imagen-4.0-fast-generate-001`) and survive untouched.

- **`status: "deprecated"` from models.dev now sets `deprecated=True`** — 128
  retired models across the catalog. They are excluded from `list_deployments()`
  and `default_deployment()` so they can never be picked for new work, but stay
  in `MODEL_PRICING_MAP` so an `llm_call_logs` row naming one still prices.
  Dropping them would have made historical spend unreadable.

  Previously the adapter ignored `status` entirely and every retired model
  arrived selectable.

## [0.3.0] — 2026-08

One theme: this package holds **facts about models**. Which model is default,
and whether "deep research" exists, are not facts — they belong to the consumer
or to nothing at all. Its own docstring already said so; the code did not.

### Added
- `set_default_deployment(capability, deployment_id)` and
  `get_default_overrides()`. A consumer now chooses its own default; the package
  keeps a fallback so `pip install visvoai-ai` still works standalone.

  Resolution is now: **consumer override → curated `DEFAULT_MODEL_FOR` → the
  `default=True` model → first enabled.**

  Deliberately module-level, not registry state: `install_catalog()` builds a
  fresh registry, so an override stored on the instance would be silently wiped
  by a consumer that set its default before installing a catalog.

  Validated when set, not at first use — an unknown id, or one that does not
  declare the capability, raises where the caller's stack still points at the
  line that set it. A `provider` filter also ignores a foreign override: asking
  for the default Anthropic chat model must not return a Gemini one.

  Before this, changing a default required a package release. It just did,
  twice.

### Removed
- **BREAKING: `Capability.DEEP_RESEARCH`.** Deep research is not something a
  model does. It is a separate *agent* — `deep-research-preview-04-2026` and
  `deep-research-max-preview-04-2026` — invoked with `agent=` rather than
  `model=`, and only through the Interactions API; Google's docs state it
  "cannot be accessed through `generate_content`".

  The capability was declared by `gemini-3-flash-preview`, named in
  `DEFAULT_MODEL_FOR`, and **read by nothing**. It asserted something untrue of
  every Gemini chat model.

  Consumers that implement deep research should name the agent directly, which
  is what the one known consumer already does.

### Changed
- `gemini-3.7-flash` is the default model, taking `default=True` from
  `gemini-3-flash-preview`. Google documents it as "our latest and most capable
  Flash model, built for complex coding, agentic workflows, and reliable
  multi-step execution".

  It also takes `default_thinking_label="Think"`. Without that the switch would
  have been a silent regression: the old default resolves to MEDIUM thinking and
  `gemini-3.7-flash` had no label, so every new chat would have dropped to
  thinking OFF — invisible in any diff of "which model is default".

  It is **not** cheaper than the model it replaces: $0.75/$3.75 against
  $0.50/$3.00, so +50% input and +25% output per token.

- `test_list_deployments_filters_and_default` asserted a literal model id while
  its own comment said it checked "the registry default model's deployment". It
  now derives the expectation from the registry, testing the rule rather than
  today's pick.

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
