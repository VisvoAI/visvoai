"""Plan A — the shadow git repo: snapshot / dedup / TRUE restore / refs / worktree /
bundle. Runs against throwaway dirs (VISVOAI_HOME + a tmp project), never the real home
or the user's own .git."""
from __future__ import annotations

import os

import pytest

from visvoai.cli import store
from visvoai.cli.checkpoints import CheckpointError, ShadowRepo

pytestmark = pytest.mark.skipif(not ShadowRepo.available(), reason="git not installed")


def _project(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "a.txt").write_text("v1\n")
    (proj / "b.txt").write_text("keep\n")
    (proj / "sub" / "c.txt").write_text("x\n")
    (proj / ".gitignore").write_text("ignored/\n")
    (proj / "ignored").mkdir()
    (proj / "ignored" / "big.txt").write_text("junk\n")
    pid = store.resolve_project_id(str(proj))
    return proj, ShadowRepo.for_project(pid, str(proj))


def test_snapshot_then_restore_reverts_modifies_undeletes_and_removes_new(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha1, made = repo.snapshot(None, "cp1")
    assert made
    # mutate: change a, add new, delete b
    (proj / "a.txt").write_text("v2\n")
    (proj / "new.txt").write_text("new\n")
    (proj / "b.txt").unlink()
    sha2, made2 = repo.snapshot(sha1, "cp2")
    assert made2 and sha2 != sha1

    repo.restore(sha1)
    assert (proj / "a.txt").read_text() == "v1\n"      # reverted
    assert (proj / "b.txt").exists()                    # un-deleted
    assert not (proj / "new.txt").exists()              # new file removed (TRUE restore)


def test_gitignore_and_default_excludes_respected(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    (proj / "node_modules").mkdir()
    (proj / "node_modules" / "x.js").write_text("//\n")
    sha, _ = repo.snapshot(None, "cp")
    tracked = repo._run("ls-tree", "-r", "--name-only", sha).splitlines()
    assert "ignored/big.txt" not in tracked       # project .gitignore
    assert "node_modules/x.js" not in tracked      # default excludes
    assert ".visvoai/config.toml" not in tracked   # our own metadata never snapshotted


def test_no_change_snapshot_dedups(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha1, _ = repo.snapshot(None, "cp1")
    sha2, made = repo.snapshot(sha1, "cp2")        # nothing changed
    assert sha2 == sha1 and made is False          # reused, no new commit


def test_refs_roundtrip_and_namespacing(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha, _ = repo.snapshot(None, "cp1")
    repo.ref_set("refs/visvoai/conv1/main", sha)
    assert repo.ref_get("refs/visvoai/conv1/main") == sha
    assert repo.refs("refs/visvoai/conv1/") == {"refs/visvoai/conv1/main": sha}
    repo.ref_delete("refs/visvoai/conv1/main")
    assert repo.ref_get("refs/visvoai/conv1/main") is None


def test_restore_prunes_emptied_dirs(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha1, _ = repo.snapshot(None, "cp1")
    (proj / "fresh").mkdir()
    (proj / "fresh" / "f.txt").write_text("z\n")
    repo.snapshot(sha1, "cp2")
    repo.restore(sha1)
    assert not (proj / "fresh").exists()           # the only file removed → dir pruned


def test_worktree_fork_materializes_a_sha(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha1, _ = repo.snapshot(None, "cp1")
    (proj / "new.txt").write_text("new\n")
    sha2, _ = repo.snapshot(sha1, "cp2")
    fork = tmp_path / "fork"
    repo.add_worktree(str(fork), sha2)
    assert (fork / "new.txt").exists()             # fork has the cp2 state
    assert (fork / "a.txt").exists()


def test_bundle_export(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    sha, _ = repo.snapshot(None, "cp1")
    repo.ref_set("refs/visvoai/conv1/main", sha)
    out = tmp_path / "out.bundle"
    repo.bundle(str(out), ["refs/visvoai/conv1/main"])
    assert out.exists() and out.stat().st_size > 0


def test_bad_sha_raises_checkpoint_error(tmp_path, monkeypatch):
    proj, repo = _project(tmp_path, monkeypatch)
    repo.snapshot(None, "cp1")
    with pytest.raises(CheckpointError):
        repo.restore("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
