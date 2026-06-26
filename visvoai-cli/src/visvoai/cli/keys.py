"""Layered API-key resolution + storage for the CLI.

Keys are resolved per provider with this precedence (highest first):

  1. exported environment variable ({PROVIDER}_API_KEY) — incl. anything a .env
     loaded into the environment; a runtime override always wins.
  2. project secrets — `<project>/.visvoai/secrets.toml` [api_keys] (gitignored).
  3. global default — `$VISVOAI_HOME/config.toml` [api_keys] (~/.visvoai).

`load_keys_into_env(cwd)` runs once at startup and fills os.environ for any key
NOT already set (so 1 wins), reading global then letting project override it. From
there everything resolves through visvoai-ai's standard env path — no api_key=
threading. The env-var name is the `{PROVIDER}_API_KEY` convention, matching the
provider map in visvoai-ai.

Secrets are written 0600; a project secrets file is auto-added to .gitignore so a
key never lands in version control.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

_SECTION = "api_keys"


def env_var_for(provider: str) -> str:
    """The environment-variable name for a provider's key ({PROVIDER}_API_KEY)."""
    return f"{provider.upper()}_API_KEY"


def _visvoai_home() -> Path:
    return Path(os.environ.get("VISVOAI_HOME") or (Path.home() / ".visvoai"))


def global_config_path() -> Path:
    return _visvoai_home() / "config.toml"


def project_secrets_path(cwd: str) -> Path:
    """`<project>/.visvoai/secrets.toml`, anchored to the nearest existing .visvoai/
    (walk-up, like git finds .git); falls back to cwd/.visvoai."""
    start = Path(cwd).resolve()
    for d in [start, *start.parents]:
        if (d / ".visvoai").is_dir():
            return d / ".visvoai" / "secrets.toml"
    return start / ".visvoai" / "secrets.toml"


def _read_keys(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    section = data.get(_SECTION, {})
    return {k: v for k, v in section.items() if isinstance(v, str) and v}


def load_keys_into_env(cwd: str) -> None:
    """Populate os.environ from the config layers for any provider key not already
    set. Project overrides global; an exported var (incl. one from .env) wins over
    both because we never overwrite an existing value."""
    merged: dict[str, str] = {}
    merged.update(_read_keys(global_config_path()))          # global
    merged.update(_read_keys(project_secrets_path(cwd)))     # project overrides global
    for provider, key in merged.items():
        var = env_var_for(provider)
        if not os.environ.get(var):   # exported / .env value wins
            os.environ[var] = key


def resolved_source(provider: str, cwd: str) -> str | None:
    """Where this provider's key resolves from right now: 'env' | 'project' |
    'global' | None. For status/UX — never returns the key itself."""
    if os.environ.get(env_var_for(provider)):
        return "env"
    if provider in _read_keys(project_secrets_path(cwd)):
        return "project"
    if provider in _read_keys(global_config_path()):
        return "global"
    return None


def _dump_toml(data: dict) -> str:
    """Serialize a shallow config dict (top-level scalars + sub-tables of strings)
    back to TOML, preserving any non-key sections. Sufficient for our key stores."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    lines: list[str] = []
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for k, v in data.items():       # top-level scalars first (e.g. project_id)
        if not isinstance(v, dict):
            lines.append(f'{k} = "{esc(str(v))}"')
    for name, table in tables.items():
        lines.append(f"\n[{name}]")
        for k, v in table.items():
            lines.append(f'{k} = "{esc(str(v))}"')
    return "\n".join(lines).strip() + "\n"


def set_key(provider: str, key: str, scope: str, cwd: str) -> Path:
    """Store a provider key. scope: 'global' → ~/.visvoai/config.toml; 'project' →
    <project>/.visvoai/secrets.toml (auto-gitignored). Preserves other content,
    writes 0600. Returns the file path."""
    path = global_config_path() if scope == "global" else project_secrets_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
    data.setdefault(_SECTION, {})[provider] = key

    path.write_text(_dump_toml(data))
    path.chmod(0o600)
    if scope == "project":
        _ensure_gitignored(path)
    return path


def _ensure_gitignored(secrets_path: Path) -> None:
    """Append the secrets file to the project's .gitignore (idempotent) so a stored
    key can never be committed. No-op outside a git repo."""
    repo = _git_root(secrets_path.parent)
    if repo is None:
        return
    rel = secrets_path.relative_to(repo).as_posix()
    gi = repo / ".gitignore"
    existing = gi.read_text().splitlines() if gi.exists() else []
    if rel in existing or ".visvoai/secrets.toml" in existing:
        return
    with gi.open("a", encoding="utf-8") as f:
        if existing and existing[-1].strip():
            f.write("\n")
        f.write(f"# visvoai stored API keys — never commit\n{rel}\n")


def _git_root(start: Path) -> Path | None:
    for d in [start.resolve(), *start.resolve().parents]:
        if (d / ".git").exists():
            return d
    return None
