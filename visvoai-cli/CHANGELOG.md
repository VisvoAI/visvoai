# Changelog — visvoai-cli

Versions follow `v0.MINOR.PATCH` while unstable (pre-1.0): MINOR for new capability or
breaking changes, PATCH for fixes. No major bump until the surface stabilizes.

## [0.2.0] — 2026-06

### Added
- **Dynamic model catalog** (`catalog.py`): at startup the CLI installs
  `build_catalog([BakedSource(), RemoteModelsDevSource(cache)])` so the model picker
  reflects the live models.dev catalog (~4000 models / ~128 providers), cached at
  `~/.visvoai/cache/models.json`, offline-tolerant via the bundled snapshot.
- `--refresh-models` flag — re-fetch the catalog (drops the cache) and exit.
- Picker filtering: shows the curated baked deployments always, plus a provider's full
  models.dev catalog only when that provider has a configured key — abundance without
  drowning the list.

### Changed
- **Model page redesigned** (`screens/model_view.py`): replaced the per-model Widget list
  (which mounted ~2000 widgets and lagged at catalog scale) with a virtualized `OptionList`
  + a live search `Input`. Type to filter by name/provider; connected-first grouping kept.
  Rows render only when visible.

### Requires
- `visvoai-ai >= 0.2.0` (catalog engine APIs).

## [0.1.0]
- Initial CLI: Textual TUI + single-shot, layered API-key storage, model/thinking picker.
