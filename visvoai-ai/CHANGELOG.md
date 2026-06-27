# Changelog — visvoai-ai

All notable changes to this package. Versions follow `v0.MINOR.PATCH` while the API is
unstable (pre-1.0): MINOR for new capability or breaking changes, PATCH for fixes. No
major (1.0) bump until the surface stabilizes.

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
