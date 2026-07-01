"""Adaptive spinner tips + the global (per-user) state that drives them: a tip is
suppressed once its feature is used, undiscovered ones surface, and a fully-fluent
user falls back to the general pool."""
from __future__ import annotations

from visvoai.cli import state
from visvoai.cli.widgets.conversation import TIP_CATALOG, adaptive_tips


def test_record_used_and_used_features(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    assert state.used_features() == set()
    state.record_used("rewind")
    state.record_used("rewind")          # idempotent
    state.record_used("branch")
    assert state.used_features() == {"rewind", "branch"}


def test_mark_shown_is_one_time(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    assert state.was_shown("coach_checkpoint") is False
    assert state.mark_shown("coach_checkpoint") is True     # first time → show
    assert state.mark_shown("coach_checkpoint") is False    # already shown
    assert state.was_shown("coach_checkpoint") is True


def test_adaptive_tips_suppresses_learned_features():
    all_tips = {t for _, t in TIP_CATALOG}
    rewind_tip = next(t for k, t in TIP_CATALOG if k == "rewind")
    # nothing learned → the rewind tip is eligible
    assert rewind_tip in set(adaptive_tips(set()))
    # rewind learned → its tip drops out (plenty of others remain)
    learned = adaptive_tips({"rewind"})
    assert rewind_tip not in set(learned)
    assert set(learned) <= all_tips and learned


def test_adaptive_tips_falls_back_to_full_pool_for_power_user():
    # every feature-keyed tip learned → too few unlearned → return the full pool
    all_keys = {k for k, _ in TIP_CATALOG if k is not None}
    pool = adaptive_tips(all_keys)
    assert set(pool) == {t for _, t in TIP_CATALOG}


def test_adaptive_tips_always_includes_general_tips():
    general = [t for k, t in TIP_CATALOG if k is None]
    tips = set(adaptive_tips({"rewind"}))
    assert all(g in tips for g in general)
