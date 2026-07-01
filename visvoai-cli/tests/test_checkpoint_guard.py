"""Guard against snapshotting the home dir / filesystem root (the 'launched visvoai in
~' trap that silently killed checkpointing) — and that the guard disables checkpointing
loudly-once instead of failing silently."""
from __future__ import annotations

from pathlib import Path

import pytest

from visvoai.cli import VisvoApp, store
from visvoai.cli.checkpoints import ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def test_home_dir_is_not_checkpointable(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home" / ".visvoai"))
    # cwd == home (the ancestor of the visvoai data dir) → disabled
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    reason = store.checkpoints_disabled_reason(str(tmp_path / "home"))
    assert reason and "home directory" in reason


def test_filesystem_root_is_not_checkpointable(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home" / ".visvoai"))
    # project_root falls back to cwd when no anchor; use "/" → vh is under it
    assert store.checkpoints_disabled_reason("/") is not None


def test_normal_project_is_checkpointable(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home" / ".visvoai"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    proj = tmp_path / "home" / "projects" / "myapp"
    proj.mkdir(parents=True)
    assert store.checkpoints_disabled_reason(str(proj)) is None


@pytest.mark.asyncio
async def test_ensure_checkpoints_disabled_and_notified_in_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home" / ".visvoai"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    app = VisvoApp()
    async with app.run_test() as pilot:
        app._cwd = str(tmp_path / "home")             # launched in the home dir
        app._project_id = store.resolve_project_id(app._cwd)
        app._conv_id = store.new_conversation_id()
        notes: list[tuple[str, str]] = []
        monkeypatch.setattr(app, "notify",
                            lambda msg, **k: notes.append((msg, k.get("severity", ""))))

        assert app._ensure_checkpoints() is None      # refused
        assert app._cp_failed is True                  # won't retry
        assert notes and "off" in notes[0][0] and notes[0][1] == "warning"
        # second call: already failed → no repo, no duplicate notice
        assert app._ensure_checkpoints() is None
        assert len(notes) == 1
