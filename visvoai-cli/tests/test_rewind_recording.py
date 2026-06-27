"""Plan B — checkpoint recording: baseline, timeline chaining, registry dedup, branch
ref/meta tracking, and resume tip-adoption. Drives RewindMixin directly (no live model)."""
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


def _timeline(app):
    return store.read_timeline(app._project_id, app._conv_id, "main")


def test_baseline_then_turn_chain_in_timeline(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(3, "turn", "first turn")

    rows = _timeline(app)
    assert [r["kind"] for r in rows] == ["baseline", "turn"]
    assert rows[0]["message_index"] == 0 and rows[1]["message_index"] == 3
    c0 = store.registry_commit(app._project_id, app._conv_id, rows[0]["checkpoint_id"])
    c1 = store.registry_commit(app._project_id, app._conv_id, rows[1]["checkpoint_id"])
    assert c0 and c1 and c0 != c1          # file changed → distinct commits


def test_no_change_turn_dedups_commit(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    app._record_checkpoint(2, "turn", "no edits")   # nothing changed on disk
    rows = _timeline(app)
    c0 = store.registry_commit(app._project_id, app._conv_id, rows[0]["checkpoint_id"])
    c1 = store.registry_commit(app._project_id, app._conv_id, rows[1]["checkpoint_id"])
    assert c0 == c1                         # same tree → reused commit


def test_branch_meta_and_ref_track_tip(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(3, "turn", "t")

    assert store.read_branch_meta(app._project_id, app._conv_id, "main")["tip"] == app._cp_tip_id
    assert app._checkpoints.ref_get(f"refs/visvoai/{app._conv_id}/main") == app._cp_tip_sha
    assert store.read_meta(app._project_id, app._conv_id)["active_branch"] == "main"


def test_resume_adopts_existing_tip_without_new_row(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    app = _app_on(proj, monkeypatch)
    app._maybe_baseline()
    app._record_checkpoint(3, "turn", "t")
    n_before = len(_timeline(app))
    tip = app._cp_tip_id

    app2 = VisvoApp()
    app2._cwd = str(proj)
    app2._project_id = app._project_id
    app2._conv_id = app._conv_id
    app2._maybe_baseline()                  # should ADOPT, not re-baseline
    assert app2._cp_tip_id == tip
    assert len(_timeline(app2)) == n_before


def test_recording_is_silent_noop_without_conversation(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    app = VisvoApp()
    app._cwd = str(proj)
    app._maybe_baseline()                   # no _conv_id → no-op, no repo
    assert app._checkpoints is None
