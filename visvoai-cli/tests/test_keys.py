"""Layered API-key resolution + storage.

Precedence (highest first): exported env > project secrets > global config. set_key
writes 0600, preserves other content, and auto-gitignores a project secrets file.
"""
import os
import stat
import tomllib

import pytest

from visvoai.cli import keys


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate the global store (VISVOAI_HOME) and a clean env per test."""
    home = tmp_path / "home"
    monkeypatch.setenv("VISVOAI_HOME", str(home))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_env_var_for():
    assert keys.env_var_for("gemini") == "GEMINI_API_KEY"
    assert keys.env_var_for("anthropic") == "ANTHROPIC_API_KEY"


def test_set_key_global_writes_table_and_resolves(env):
    proj = env / "proj"
    proj.mkdir()
    path = keys.set_key("gemini", "g-123", "global", str(proj))
    assert path == keys.global_config_path()
    data = tomllib.loads(path.read_text())
    assert data["api_keys"]["gemini"] == "g-123"
    keys.load_keys_into_env(str(proj))
    assert os.environ["GEMINI_API_KEY"] == "g-123"


def test_project_overrides_global(env):
    proj = env / "proj"
    (proj / ".visvoai").mkdir(parents=True)
    keys.set_key("gemini", "GLOBAL", "global", str(proj))
    keys.set_key("gemini", "PROJECT", "project", str(proj))
    keys.load_keys_into_env(str(proj))
    assert os.environ["GEMINI_API_KEY"] == "PROJECT"


def test_exported_env_wins_over_stored(env, monkeypatch):
    proj = env / "proj"
    proj.mkdir()
    keys.set_key("gemini", "STORED", "global", str(proj))
    monkeypatch.setenv("GEMINI_API_KEY", "EXPORTED")
    keys.load_keys_into_env(str(proj))   # must NOT overwrite an exported value
    assert os.environ["GEMINI_API_KEY"] == "EXPORTED"


def test_set_key_project_is_0600_and_gitignored(env):
    proj = env / "repo"
    (proj / ".git").mkdir(parents=True)   # make it a git repo
    proj.mkdir(exist_ok=True)
    path = keys.set_key("gemini", "p-1", "project", str(proj))
    assert path == proj / ".visvoai" / "secrets.toml"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    gi = (proj / ".gitignore").read_text()
    assert ".visvoai/secrets.toml" in gi


def test_set_key_preserves_other_content(env):
    proj = env / "proj"
    proj.mkdir()
    keys.set_key("gemini", "g", "global", str(proj))
    keys.set_key("anthropic", "a", "global", str(proj))   # second key, same file
    data = tomllib.loads(keys.global_config_path().read_text())
    assert data["api_keys"] == {"gemini": "g", "anthropic": "a"}


def test_resolved_source(env, monkeypatch):
    proj = env / "proj"
    (proj / ".visvoai").mkdir(parents=True)
    assert keys.resolved_source("gemini", str(proj)) is None
    keys.set_key("gemini", "g", "global", str(proj))
    assert keys.resolved_source("gemini", str(proj)) == "global"
    keys.set_key("gemini", "p", "project", str(proj))
    assert keys.resolved_source("gemini", str(proj)) == "project"
    monkeypatch.setenv("GEMINI_API_KEY", "e")
    assert keys.resolved_source("gemini", str(proj)) == "env"
