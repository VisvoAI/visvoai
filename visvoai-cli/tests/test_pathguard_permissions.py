"""Path confinement (pathguard) and the permission policy (permissions)."""
from __future__ import annotations

import os

import pytest

from visvoai.cli.pathguard import PathDenied, confine, resolve_roots
from visvoai.cli.permissions import PermissionPolicy, load_policy
from visvoai.cli.tools import build_cli_tools


# ---- pathguard ----------------------------------------------------------------

def test_in_root_resolves(tmp_path):
    roots = resolve_roots(str(tmp_path))
    out = confine("sub/file.txt", roots)
    assert out == os.path.realpath(str(tmp_path / "sub" / "file.txt"))


@pytest.mark.parametrize("bad", ["../escape.txt", "../../etc/passwd", "/etc/passwd"])
def test_escapes_blocked(tmp_path, bad):
    roots = resolve_roots(str(tmp_path))
    with pytest.raises(PathDenied):
        confine(bad, roots)


def test_git_internals_blocked(tmp_path):
    roots = resolve_roots(str(tmp_path))
    with pytest.raises(PathDenied):
        confine(".git/config", roots)


def test_symlink_escape_blocked(tmp_path):
    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    link = tmp_path / "link"
    os.symlink(outside, link)
    roots = resolve_roots(str(tmp_path))
    with pytest.raises(PathDenied):
        confine("link/loot.txt", roots)  # resolves out of root via the symlink


def test_extra_write_root_allows(tmp_path):
    sibling = tmp_path.parent / "sib"
    sibling.mkdir()
    # config-driven extra root
    vis = tmp_path / ".visvoai"
    vis.mkdir()
    (vis / "config.toml").write_text(
        f'[permissions]\nwrite_roots = ["{sibling}"]\n'
    )
    roots = resolve_roots(str(tmp_path))
    out = confine(str(sibling / "x.txt"), roots)
    assert out.startswith(os.path.realpath(str(sibling)))


def test_write_tool_returns_error_not_raise(tmp_path):
    wf = {t.name: t for t in build_cli_tools(cwd=str(tmp_path))}["write_file"]
    assert wf.invoke({"path": "/etc/nope", "content": "x"}).startswith("ERROR")
    assert "Wrote" in wf.invoke({"path": "ok.txt", "content": "x"})


# ---- permissions --------------------------------------------------------------

def test_shell_prefix_match():
    p = PermissionPolicy(allow_shell=["git status", "ls"], allow_write=[])
    assert p.auto_allow("run_shell", {"command": "git status -s"})
    assert p.auto_allow("run_shell", {"command": "ls"})
    assert not p.auto_allow("run_shell", {"command": "git push"})
    assert not p.auto_allow("run_shell", {"command": "lsof"})  # prefix must be word-bounded


def test_write_glob_match():
    p = PermissionPolicy(allow_shell=[], allow_write=["*.md", "docs/**"])
    assert p.auto_allow("write_file", {"path": "README.md"})
    assert p.auto_allow("edit_file", {"path": "docs/guide/intro.txt"})
    assert not p.auto_allow("write_file", {"path": "src/main.py"})


def test_unknown_tool_never_auto_allowed():
    p = PermissionPolicy(allow_shell=["x"], allow_write=["*"])
    assert not p.auto_allow("read_file", {"path": "anything"})


def test_load_policy_layers_global_and_project(tmp_path):
    vis = tmp_path / ".visvoai"
    vis.mkdir()
    (vis / "config.toml").write_text('[permissions]\nallow_shell = ["pytest"]\n')
    p = load_policy(str(tmp_path))
    assert p.auto_allow("run_shell", {"command": "pytest -q"})


def test_load_policy_empty_when_absent(tmp_path):
    p = load_policy(str(tmp_path))
    assert not p.auto_allow("run_shell", {"command": "anything"})
