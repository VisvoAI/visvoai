"""Plan F + G — fork (worktree + seeded conversation) and export (transcript / bundle).
Exercises the testable cores (_do_fork / _do_export), skipping the interactive pickers."""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _row(app, label):
    rows = store.read_timeline(app._project_id, app._conv_id, "main")
    return next(r for r in rows if r["label"] == label)


def _conv(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._history += [HumanMessage(content="build a parser"), AIMessage(content="done")]
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(2, "turn", "build a parser")
    store.append_receipt(app._project_id, app._conv_id, {"seconds": 1, "model": "m", "cost": 0.1})
    store.save_conversation(app._project_id, app._conv_id, app._history)
    return proj, app


def test_fork_materializes_worktree_and_seeds_conversation(tmp_path, monkeypatch):
    proj, app = _conv(tmp_path, monkeypatch)
    app._history += [HumanMessage(content="q2"), AIMessage(content="a2")]
    (proj / "a.txt").write_text("v3\n")
    app._record_checkpoint(4, "turn", "q2")
    store.save_conversation(app._project_id, app._conv_id, app._history)

    turn1 = _row(app, "build a parser")
    fork_dir = tmp_path / "fork"
    fork_cid = app._do_fork(turn1, str(fork_dir))

    assert fork_cid is not None
    assert (fork_dir / "a.txt").read_text() == "v2\n"          # worktree at turn1 code
    fork_pid = store.resolve_project_id(str(fork_dir))
    seeded = store.load_conversation(fork_pid, fork_cid)
    assert len(seeded) == 2                                     # thread truncated to turn1


def test_export_transcript_writes_markdown(tmp_path, monkeypatch):
    proj, app = _conv(tmp_path, monkeypatch)
    out = tmp_path / "out.md"
    path = app._do_export("transcript", str(out))
    assert path == str(out)
    text = out.read_text()
    assert "## You" in text and "build a parser" in text and "## Assistant" in text


def test_export_bundle_writes_self_contained_dir(tmp_path, monkeypatch):
    proj, app = _conv(tmp_path, monkeypatch)
    out = tmp_path / "export.visvoexport"
    path = app._do_export("bundle", str(out))
    assert path == str(out)
    assert (out / "transcript.md").exists()
    assert (out / "thread.jsonl").exists()
    assert (out / "code.bundle").exists() and (out / "code.bundle").stat().st_size > 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["messages"] == 2 and manifest["code_bundle"] is True
