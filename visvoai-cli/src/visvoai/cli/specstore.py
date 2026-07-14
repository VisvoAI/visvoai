"""
LayeredSpecStore — the ONE implementation of the pattern MCP servers, agents,
and skills all share: definitions merged from ordered layers (later wins on
name) with spec-hash trust for layers the user doesn't control.

Layers are PROVIDERS, not hardcoded directories — a layer is any callable
returning name→spec plus a tier label and an identity path. That keeps the
door open for non-file layers later (the platform's DB-backed Effective*
registries have exactly this shape).

Generic mechanics owned here, once:
  · merge precedence (layer list order; later wins on name)
  · the coincident-layer guard — outside any project, project_root() can
    resolve to $HOME (its anchor walk matches the global ~/.visvoai/config.toml),
    making the "project" layer the global dir itself; loading the same identity
    twice would reclassify user-authored definitions as project-defined
    (spurious trust prompts). Identity dedupe kills the whole bug class.
  · trust records: ~/.visvoai/projects/<pid>/<kind>_trust.toml, `[trusted]`
    name = "<spec_hash>" — one-time approval per exact definition; any change
    re-prompts. Specs from trusted TIERS (user-authored) skip the check.

A spec only needs: `.name`, `.source` (set from its layer's tier), and
`.spec_hash()`. Domain modules keep parsing, tool-building, and everything
else that actually differs.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar

SpecT = TypeVar("SpecT")


@dataclass(frozen=True)
class Layer(Generic[SpecT]):
    source: str                                  # tier stamped on specs ("global"…)
    trusted: bool                                # tier implicitly trusted?
    load: Callable[[], dict[str, SpecT]]         # name → spec (source already set)
    identity: Path | None = None                 # dedupe key; None = always loads


class LayeredSpecStore(Generic[SpecT]):
    def __init__(self, kind: str, cwd: str, layers: list[Layer[SpecT]]) -> None:
        self.kind = kind
        self.cwd = cwd
        self.layers = layers
        self._trusted_tiers = {l.source for l in layers if l.trusted}

    # ── loading ───────────────────────────────────────────────────────────────
    def load(self) -> dict[str, SpecT]:
        merged: dict[str, SpecT] = {}
        seen: set[Path] = set()
        for layer in self.layers:
            if layer.identity is not None:
                key = layer.identity.resolve()
                if key in seen:          # coincident-layer guard
                    continue
                seen.add(key)
            merged.update(layer.load())
        return merged

    # ── trust ─────────────────────────────────────────────────────────────────
    def _trust_path(self) -> Path:
        from visvoai.cli.store import resolve_project_id, visvoai_home
        return (visvoai_home() / "projects" / resolve_project_id(self.cwd)
                / f"{self.kind}_trust.toml")

    def _read_trust(self) -> dict[str, str]:
        path = self._trust_path()
        if not path.exists():
            return {}
        try:
            return {k: v for k, v in
                    (tomllib.loads(path.read_text()).get("trusted") or {}).items()
                    if isinstance(v, str)}
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def is_trusted(self, spec: SpecT) -> bool:
        if getattr(spec, "source") in self._trusted_tiers:
            return True
        return self._read_trust().get(spec.name) == spec.spec_hash()

    def trust(self, spec: SpecT) -> None:
        trusted = self._read_trust()
        trusted[spec.name] = spec.spec_hash()
        path = self._trust_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[trusted]"] + [f'{n} = "{h}"' for n, h in sorted(trusted.items())]
        path.write_text("\n".join(lines) + "\n")

    def untrusted(self) -> list[SpecT]:
        return [s for s in self.load().values() if not self.is_trusted(s)]
