"""Plan D — resume into a drifted work tree: adopt the tip, and record a baseline of
current reality when the tree changed out-of-session. Plus the baseline-crossing warn."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _seed_conversation(tmp_path, monkeypatch):
    """A conversation with a baseline + one turn checkpoint; returns (proj, pid, cid)."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(2, "turn", "q1")
    store.save_conversation(app._project_id, app._conv_id, app._history)
    return proj, app._project_id, app._conv_id


def _resumed_app(proj, pid, cid):
    app = VisvoApp()
    app._cwd = str(proj)
    app._project_id = pid
    app._conv_id = cid
    app._history = list(store.load_conversation(pid, cid))
    return app


def test_resume_with_drift_records_baseline(tmp_path, monkeypatch):
    proj, pid, cid = _seed_conversation(tmp_path, monkeypatch)
    n_before = len(store.read_checkpoints(pid, cid))
    (proj / "a.txt").write_text("hand-edited between sessions\n")   # external drift

    app = _resumed_app(proj, pid, cid)
    app._resume_checkpoints()

    cps = store.read_checkpoints(pid, cid)
    assert len(cps) == n_before + 1
    drift = cps[-1]
    assert drift["kind"] == "baseline"
    assert drift["message_index"] == len(app._history)   # anchored at the thread end
    assert app._cp_tip_id == drift["id"]                  # tip advanced to reality


def test_resume_without_drift_adopts_tip_no_new_checkpoint(tmp_path, monkeypatch):
    proj, pid, cid = _seed_conversation(tmp_path, monkeypatch)
    n_before = len(store.read_checkpoints(pid, cid))

    app = _resumed_app(proj, pid, cid)            # tree untouched
    app._resume_checkpoints()

    assert len(store.read_checkpoints(pid, cid)) == n_before   # nothing added
    assert app._cp_tip_sha is not None                          # but tip adopted


def test_rewind_crosses_baseline_detects_resume_point(tmp_path, monkeypatch):
    proj, pid, cid = _seed_conversation(tmp_path, monkeypatch)
    (proj / "a.txt").write_text("drift\n")
    app = _resumed_app(proj, pid, cid)
    app._resume_checkpoints()                      # appends a baseline after the turn cp

    records = store.read_checkpoints(pid, cid)
    chain = app._active_chain(records)
    turn1 = next(c for c in records if c["label"] == "q1")
    # the resume baseline sits AFTER turn1 in the chain → rewinding to turn1 crosses it
    assert app._rewind_crosses_baseline(chain, turn1) is True
    # rewinding to the latest (the baseline itself) crosses nothing
    assert app._rewind_crosses_baseline(chain, chain[-1]) is False
