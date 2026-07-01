"""Branch-switch / fork-from must not silently overwrite uncommitted hand-edits: the
current branch's working-tree drift is snapshotted before the restore, so it's
recoverable via /rewind."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _row(app, label):
    rows = store.read_timeline(app._project_id, app._conv_id, app._cp_branch)
    return next(r for r in rows if r["label"] == label)


async def _two_branches(app, proj):
    app._cwd = str(proj)
    app._project_id = store.resolve_project_id(str(proj))
    app._conv_id = store.new_conversation_id()
    app._maybe_baseline()
    app._history += [HumanMessage(content="q1"), AIMessage(content="a1")]
    (proj / "a.txt").write_text("v2\n")
    app._record_checkpoint(2, "turn", "q1")
    store.write_branch_thread(app._project_id, app._conv_id, "main", app._history)
    await app._branch_from(_row(app, "q1"), "alt")   # now on alt


@pytest.mark.asyncio
async def test_switch_snapshots_uncommitted_edits(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_branches(app, proj)
        await pilot.pause()

        # hand-edit on alt (NO turn → no checkpoint captured it), then switch to main
        (proj / "a.txt").write_text("HAND-EDITED\n")
        n_before = len(store.read_timeline(app._project_id, app._conv_id, "alt"))
        await app._switch_branch("main")
        await pilot.pause()

        # a drift checkpoint was recorded on alt (the branch we left)
        alt_rows = store.read_timeline(app._project_id, app._conv_id, "alt")
        assert len(alt_rows) == n_before + 1
        assert alt_rows[-1]["kind"] == "edit"

        # switching back to alt restores the hand-edited content (not lost)
        await app._switch_branch("alt")
        await pilot.pause()
        assert (proj / "a.txt").read_text() == "HAND-EDITED\n"


@pytest.mark.asyncio
async def test_clean_switch_records_no_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"; proj.mkdir(); (proj / "a.txt").write_text("v1\n")
    app = VisvoApp()
    async with app.run_test() as pilot:
        await _two_branches(app, proj)
        await pilot.pause()
        n_before = len(store.read_timeline(app._project_id, app._conv_id, "alt"))
        await app._switch_branch("main")             # tree matches tip → nothing to snapshot
        await pilot.pause()
        assert len(store.read_timeline(app._project_id, app._conv_id, "alt")) == n_before
