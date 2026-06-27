"""Plan B — checkpoint recording: baseline, chained snapshots, dedup, branch refs,
and resume tip-adoption. Drives the RewindMixin methods directly (no live model)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _app_on(proj, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(proj.parent / "home"))
    app = VisvoApp()
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    return app


def _proj(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("v1\n")
    return proj


def test_baseline_then_turn_chains_with_parent_links(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(3, "turn", "first turn")

    cps = store.read_checkpoints(app._project_id, app._conv_id)
    assert [c["kind"] for c in cps] == ["baseline", "turn"]
    assert cps[0]["parent"] is None
    assert cps[1]["parent"] == cps[0]["id"]      # chained
    assert cps[1]["commit"] != cps[0]["commit"]  # file changed → distinct commit
    assert cps[0]["message_index"] == 0 and cps[1]["message_index"] == 3


def test_no_change_turn_dedups_commit(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    app._record_checkpoint(2, "turn", "no edits")   # nothing changed on disk
    cps = store.read_checkpoints(app._project_id, app._conv_id)
    assert cps[1]["commit"] == cps[0]["commit"]      # same tree → reused commit


def test_branch_ref_tracks_tip(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(3, "turn", "t")
    repo = app._checkpoints
    assert repo.ref_get(f"refs/visvoai/{app._conv_id}/main") == app._cp_tip_sha
    meta = store.read_meta(app._project_id, app._conv_id)
    assert meta["active_branch"] == "main"
    assert meta["branch_tips"]["main"] == app._cp_tip_id


def test_resume_adopts_existing_tip_without_rebaseline(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    app._record_checkpoint(3, "turn", "t")
    n_before = len(store.read_checkpoints(app._project_id, app._conv_id))
    tip = app._cp_tip_id

    # a fresh app resuming the same conversation
    app2 = VisvoApp()
    app2._cwd = str(proj)
    app2._project_id = app._project_id
    app2._conv_id = app._conv_id
    app2._maybe_baseline()                       # should ADOPT, not re-baseline
    assert app2._cp_tip_id == tip
    assert len(store.read_checkpoints(app2._project_id, app2._conv_id)) == n_before


def test_recording_is_silent_noop_without_conversation(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    app = VisvoApp()
    app._cwd = str(proj)
    # no _conv_id resolved → must not raise, must not create a repo
    app._maybe_baseline()
    assert app._checkpoints is None
