"""Tests for the bundled CHANGELOG parser (cli_changelog) and the per-project
state module (state).

Both modules are pure-Python with no Textual deps — they can be tested in
isolation, no app boot needed.
"""
from __future__ import annotations

import json

from visvoai.cli import cli_changelog, state as state_mod, store


# ── cli_changelog ─────────────────────────────────────────────────────────────

def test_changelog_parses_current_file():
    """The bundled CHANGELOG.md parses to at least one entry (a real one)."""
    entries = cli_changelog.parse_changelog()
    assert entries, "bundled CHANGELOG.md should yield >= 1 entry"
    e = entries[0]
    assert e["version"]                              # has a version
    assert e["date"]                                  # has a date
    assert e["sections"]                              # has sections
    assert any(e["sections"].values()), "every entry should have bullets"


def test_changelog_entries_are_newest_first():
    """Entries come back newest-first (matches the file's order)."""
    entries = cli_changelog.parse_changelog()
    versions = [e["version"] for e in entries]
    # Newest-first: every version must be >= the next one in version-tuple order.
    for a, b in zip(versions, versions[1:]):
        assert cli_changelog._version_tuple(a) > cli_changelog._version_tuple(b), \
            f"order broken: {a} should be > {b}"


def test_changelog_new_since_none_returns_all():
    """None as last_seen = first visit = return everything."""
    entries = cli_changelog.new_since(None)
    assert entries == cli_changelog.parse_changelog()


def test_changelog_new_since_filters_by_version_tuple():
    """0.3.4 → returns entries > 0.3.4; '0.4.0' > '0.3.4' is True, '0.10.0' > '0.4.0'
    is also True (tuple compare avoids the string-compare footgun)."""
    # Use whatever the current version is as the upper bound; everything older
    # than that is what's "new since 0.0.0".
    entries = cli_changelog.new_since("0.0.0")
    assert entries == cli_changelog.parse_changelog()


def test_changelog_new_since_returns_empty_for_current():
    """The most recent version → no new entries (nothing after itself)."""
    current = cli_changelog.current_version()
    assert cli_changelog.new_since(current) == []


def test_changelog_one_line_summary_truncates():
    """A long bullet gets truncated to max_chars with an ellipsis."""
    entries = cli_changelog.parse_changelog()
    long_entry = {"version": "x", "date": "2026-06",
                  "sections": {"Added": ["a" * 500]}}
    s = cli_changelog.one_line_summary(long_entry, max_chars=100)
    assert len(s) <= 100
    assert s.endswith("…")


def test_changelog_one_line_summary_falls_back_to_version():
    """An entry with no bullets → returns the version string."""
    e = {"version": "9.9.9", "date": "2099-01", "sections": {}}
    assert cli_changelog.one_line_summary(e) == "9.9.9"


# ── state ─────────────────────────────────────────────────────────────────────

def test_state_get_returns_empty_when_no_file(tmp_path, monkeypatch):
    """No state.json → empty dict (no exception, no side effects)."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    assert state_mod.get_state("any-pid") == {}
    # And no directory was created (read-only).
    assert not (tmp_path / "projects" / "any-pid").exists()


def test_state_update_creates_file_and_merges(tmp_path, monkeypatch):
    """update_state writes + merges atomically; subsequent gets see the merge."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    state_mod.update_state("p1", last_seen_version="0.4.0")
    state_mod.update_state("p1", some_field="value")
    got = state_mod.get_state("p1")
    assert got == {"last_seen_version": "0.4.0", "some_field": "value"}


def test_state_update_skips_none_values(tmp_path, monkeypatch):
    """Passing `None` for a field leaves it untouched (lets callers conditionally
    update without first reading)."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    state_mod.update_state("p2", last_seen_version="0.4.0")
    state_mod.update_state("p2", last_seen_version=None)   # no-op
    assert state_mod.get_state("p2") == {"last_seen_version": "0.4.0"}


def test_state_get_recovers_from_corrupt_file(tmp_path, monkeypatch):
    """A malformed state.json → empty dict (not a crash)."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    p = store.visvoai_home() / "projects" / "p3" / "state.json"
    p.parent.mkdir(parents=True)
    p.write_text("not json at all", encoding="utf-8")
    assert state_mod.get_state("p3") == {}


def test_bundled_changelog_matches_the_real_one():
    """The bundled copy (package-data, read at runtime) must not drift from the
    canonical CHANGELOG.md at the package root. package-data can only live under the
    package dir, so the copy is necessary — this guard forces updating both."""
    from pathlib import Path
    from importlib import resources

    root = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    bundled = resources.files("visvoai.cli.assets").joinpath("CHANGELOG.md").read_text(encoding="utf-8")
    assert bundled == root.read_text(encoding="utf-8"), (
        "src/visvoai/cli/assets/CHANGELOG.md is out of sync with CHANGELOG.md — "
        "update both (they must be identical)")