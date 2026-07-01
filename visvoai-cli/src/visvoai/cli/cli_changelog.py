"""cli_changelog.py — Parse the bundled CHANGELOG and surface new entries.

The CHANGELOG is shipped as package data (`src/visvoai/cli/assets/CHANGELOG.md`,
picked up by `pyproject.toml`'s `[tool.setuptools.package-data]` `assets/*` glob).
The format is small and hand-curated, so parsing is regex-based — fragile to
silent drift, but a unit test asserts the bundled file parses cleanly.

Schema: `## [X.Y.Z] — YYYY-MM` headers + `### Added/Changed/Fixed/...` sections
under each + bullet lines. Entries are returned newest-first.
"""
from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources


_VERSION_RE = re.compile(r"^## \[(?P<v>[\d.]+)\] — (?P<d>\d{4}-\d{2})")
_SECTION_RE = re.compile(r"^### (?P<kind>Added|Changed|Fixed|Removed|Requires|Deprecated)")


@lru_cache(maxsize=1)
def _read_changelog_text() -> str:
    """Load the bundled CHANGELOG.md. Cached — parsed on first call. Lazy
    (not at import time) so unit tests can monkeypatch if needed."""
    return resources.files("visvoai.cli.assets").joinpath("CHANGELOG.md").read_text(encoding="utf-8")


def current_version() -> str:
    """The package's runtime version (from installed metadata)."""
    from importlib.metadata import version as _v
    return _v("visvoai-cli")


def parse_changelog() -> list[dict]:
    """Entries newest-first.

    Each entry: {"version": "0.4.0", "date": "2026-06",
                 "sections": {"Added": [...bullets...], "Fixed": [...], ...}}

    Unknown section headers are captured so they don't disappear silently. A
    bullet that sits under no section (a stray lead-in) is dropped.
    """
    text = _read_changelog_text()
    entries: list[dict] = []
    current: dict | None = None
    section: str | None = None
    for line in text.splitlines():
        m = _VERSION_RE.match(line)
        if m:
            if current is not None:
                entries.append(current)
            current = {"version": m.group("v"), "date": m.group("d"), "sections": {}}
            section = None
            continue
        if current is None:
            continue   # preamble (the file header) — ignore
        m = _SECTION_RE.match(line)
        if m:
            section = m.group("kind")
            current["sections"].setdefault(section, [])
            continue
        if section and line.startswith("- "):
            current["sections"][section].append(line[2:])
    if current is not None:
        entries.append(current)
    return entries


def _version_tuple(v: str) -> tuple[int, ...]:
    """Tuple form for ordering: ('0', '4', '0') vs ('0', '10', '0') — a naive
    string compare would say '0.10.0' < '0.4.0'. Tuple compare is correct."""
    return tuple(int(x) for x in v.split("."))


def new_since(last_seen: str | None) -> list[dict]:
    """Entries with version > `last_seen`. If `last_seen` is None (first visit),
    returns ALL entries (the user hasn't seen anything yet)."""
    entries = parse_changelog()
    if last_seen is None:
        return entries
    seen = _version_tuple(last_seen)
    return [e for e in entries if _version_tuple(e["version"]) > seen]


def one_line_summary(entry: dict, max_chars: int = 200) -> str:
    """The first bullet of the first non-empty section of `entry`, truncated.
    Used for the compact 'what's new' line in the welcome card."""
    for kind, bullets in entry["sections"].items():
        if bullets:
            text = bullets[0]
            if len(text) > max_chars:
                return text[:max_chars - 1] + "…"
            return text
    return entry["version"]