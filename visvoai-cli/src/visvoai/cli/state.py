"""state.py — Per-project UI state (NOT project config).

Lives at `~/.visvoai/projects/<pid>/state.json` — global, never in-repo, so it
doesn't pollute the project or get committed. Currently tracks:

- `last_seen_version` — the last CHANGELOG version the user has been shown
  (Commit D); used to drive the "what's new since last visit" panel.

The schema is open-ended; new fields extend it without a migration (a JSON
read returns `{}` when the file is absent, so callers always see a dict).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from visvoai.cli import store


def _state_path(project_id: str) -> Path:
    """The state.json path for a project. Pure path computation — does NOT
    create the directory (caller decides whether a write warrants a mkdir)."""
    return store.visvoai_home() / "projects" / project_id / "state.json"


def get_state(project_id: str) -> dict:
    """Read the per-project state. Returns `{}` when no state file exists OR the
    file is corrupt — never raises. Reading does NOT create the file or any
    directory (welcome-banner safe)."""
    p = _state_path(project_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def update_state(project_id: str, **fields) -> dict:
    """Merge `fields` into the per-project state and atomically rewrite (write to
    a sibling `.tmp` then `os.replace`). Creates the parent directory on first
    write. Fields whose value is `None` are skipped (lets callers conditionally
    update)."""
    p = _state_path(project_id)
    state = get_state(project_id)
    state.update({k: v for k, v in fields.items() if v is not None})
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return state


# ── global (per-user) state: learned features + one-time flags ───────────────
# Lives at `~/.visvoai/state.json` (NOT per-project). A user who learned /rewind in
# one project knows it everywhere, so adaptive tips + coachmarks are user-scoped.
def _global_path() -> Path:
    return store.visvoai_home() / "state.json"


def get_global() -> dict:
    """The per-user state (never raises; {} when absent/corrupt)."""
    p = _global_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_global(state: dict) -> None:
    p = _global_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def used_features() -> set[str]:
    """The set of feature keys the user has exercised at least once."""
    return set(get_global().get("used", []))


def record_used(feature: str) -> None:
    """Mark a feature as used (idempotent). Drives adaptive tips — once a feature is
    learned, its tip stops showing and an undiscovered one surfaces instead."""
    state = get_global()
    used = set(state.get("used", []))
    if feature in used:
        return
    used.add(feature)
    state["used"] = sorted(used)
    try:
        _write_global(state)
    except OSError:
        pass   # best-effort — a missed write just re-shows a tip the user knows


def was_shown(key: str) -> bool:
    """True if a one-time coachmark `key` has already been shown."""
    return key in set(get_global().get("shown", []))


def mark_shown(key: str) -> bool:
    """Mark a one-time coachmark as shown. Returns True if this call is the FIRST
    time (caller should show it now), False if already shown."""
    state = get_global()
    shown = set(state.get("shown", []))
    if key in shown:
        return False
    shown.add(key)
    state["shown"] = sorted(shown)
    try:
        _write_global(state)
    except OSError:
        return False
    return True