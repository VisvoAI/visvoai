"""
visvoai.cli.context.config — layered config for the context pipeline.

Two layers, project overrides global (same model + paths as keys.py):
  global  — `$VISVOAI_HOME/config.toml`  → [context] table
  project — `<project>/.visvoai/context.toml` → [context] table (walk-up anchored)

Schema:
    [context]
    budget_tokens = 8000              # global cap on the assembled prompt

    [context.providers.project_instructions]
    enabled = true
    order = 10
    budget_tokens = 3000

Unknown providers and unknown keys are ignored; malformed/missing files are
treated as empty. Config NEVER raises into the build path.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Sequence

from ..keys import global_config_path
from .protocol import ContextProvider

DEFAULT_GLOBAL_BUDGET = 8000


def _project_context_path(cwd: str) -> Path:
    """`<project>/.visvoai/context.toml`, anchored to the nearest existing
    .visvoai/ walking up from cwd (falls back to cwd/.visvoai)."""
    start = Path(cwd).resolve()
    for d in (start, *start.parents):
        if (d / ".visvoai").is_dir():
            return d / ".visvoai" / "context.toml"
    return start / ".visvoai" / "context.toml"


def _read_context_table(path: Path) -> dict:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    table = data.get("context")
    return table if isinstance(table, dict) else {}


def _merge(base: dict, overlay: dict) -> dict:
    """Deep-merge overlay into base (one level into `providers`); overlay wins."""
    for k, v in overlay.items():
        if k == "providers" and isinstance(v, dict) and isinstance(base.get(k), dict):
            for pname, pcfg in v.items():
                base[k][pname] = {**base[k].get(pname, {}), **pcfg}
        else:
            base[k] = v
    return base


def load_context_config(cwd: str) -> dict:
    """The merged [context] config for cwd (project over global). {} if neither set."""
    merged: dict = {}
    _merge(merged, _read_context_table(global_config_path()))
    _merge(merged, _read_context_table(_project_context_path(cwd)))
    return merged


def apply_to_providers(providers: Sequence[ContextProvider], config: dict) -> None:
    """Override enabled/order/budget_tokens on each provider from config, in place.
    Bad types are skipped silently — a typo never crashes the agent."""
    pcfg = config.get("providers", {})
    if not isinstance(pcfg, dict):
        return
    for p in providers:
        c = pcfg.get(p.name)
        if not isinstance(c, dict):
            continue
        if isinstance(c.get("enabled"), bool):
            p.enabled = c["enabled"]
        if isinstance(c.get("order"), int):
            p.order = c["order"]
        if isinstance(c.get("budget_tokens"), int):
            p.budget_tokens = c["budget_tokens"]


def global_budget(config: dict) -> int:
    v = config.get("budget_tokens")
    return v if isinstance(v, int) and v > 0 else DEFAULT_GLOBAL_BUDGET
