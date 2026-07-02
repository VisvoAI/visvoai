"""
MCP (Model Context Protocol) servers for the CLI.

Config — `[mcp_servers.<name>]` tables, two layers merged (project wins on name):

  ~/.visvoai/config.toml              global: personal servers, everywhere
  <project>/.visvoai/config.toml      project: shareable, may be checked in

  [mcp_servers.github]                stdio: CLI spawns the subprocess
  command = "npx"
  args = ["-y", "@modelcontextprotocol/server-github"]
  env = { GITHUB_TOKEN = "${GITHUB_TOKEN}" }

  [mcp_servers.linear]                remote: streamable HTTP
  url = "https://mcp.linear.app/mcp"
  headers = { Authorization = "Bearer ${LINEAR_API_KEY}" }

Secrets never live in the server table — `${VAR}` values expand from the
environment, which the layered key system (keys.py) fills at startup.

Trust — a project config is repo-controlled, and a stdio server executes a
subprocess. Project-defined servers therefore need one-time approval, recorded
per project OUTSIDE the repo (`~/.visvoai/projects/<pid>/mcp_trust.toml`) as a
hash of the server spec — any change to the spec re-prompts. Global servers are
implicitly trusted (the user wrote them).

Discovery — connect + tools/list once per session (module cache); each server
gets an independent timeout so one dead server can't hang the TUI. Tools are
exposed as LangChain tools named `server__tool` (platform convention). Protocol
transport (stdio spawn, HTTP/SSE) is entirely langchain-mcp-adapters / the
official mcp SDK — no protocol code here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SECTION = "mcp_servers"
_CONNECT_TIMEOUT_S = 10.0

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


# ── Config loading ────────────────────────────────────────────────────────────

@dataclass
class MCPServerSpec:
    name: str
    source: str                      # "global" | "project"
    command: Optional[str] = None    # stdio
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None        # remote (streamable HTTP)
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    @property
    def transport(self) -> str:
        return "stdio" if self.command else "streamable_http"

    def spec_hash(self) -> str:
        """Stable hash of the executable surface — used for trust records.
        Env/header VALUES are excluded: they hold expanded secrets, and a rotated
        token must not invalidate trust. Names are included (a new env var to a
        subprocess is a behavior change worth re-prompting for)."""
        surface = {
            "command": self.command,
            "args": self.args,
            "env_keys": sorted(self.env),
            "url": self.url,
            "header_keys": sorted(self.headers),
        }
        return hashlib.sha256(json.dumps(surface, sort_keys=True).encode()).hexdigest()[:16]


def _expand(value: str) -> str:
    """Expand ${VAR} from the environment; unknown vars become '' (a missing
    token should fail auth loudly at the server, not leak the literal '${X}')."""
    return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)


def _parse_section(path: Path, source: str) -> dict[str, MCPServerSpec]:
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("mcp: unreadable config %s: %s", path, e)
        return {}
    out: dict[str, MCPServerSpec] = {}
    for name, spec in (data.get(_SECTION) or {}).items():
        if not isinstance(spec, dict):
            continue
        command, url = spec.get("command"), spec.get("url")
        if not command and not url:
            logger.warning("mcp: server '%s' in %s has neither command nor url — skipped", name, path)
            continue
        out[name] = MCPServerSpec(
            name=name,
            source=source,
            command=command,
            args=[str(a) for a in spec.get("args", [])],
            env={k: _expand(str(v)) for k, v in (spec.get("env") or {}).items()},
            url=url,
            headers={k: _expand(str(v)) for k, v in (spec.get("headers") or {}).items()},
            enabled=bool(spec.get("enabled", True)),
        )
    return out


def load_mcp_servers(cwd: str) -> dict[str, MCPServerSpec]:
    """Merged server specs: global ∪ project, project overriding on name."""
    from visvoai.cli.keys import global_config_path
    from visvoai.cli.store import project_root

    merged = _parse_section(global_config_path(), "global")
    try:
        proj_cfg = project_root(cwd) / ".visvoai" / "config.toml"
    except Exception:
        proj_cfg = Path(cwd) / ".visvoai" / "config.toml"
    merged.update(_parse_section(proj_cfg, "project"))
    return merged


# ── Trust ─────────────────────────────────────────────────────────────────────

def _trust_path(cwd: str) -> Path:
    from visvoai.cli.store import resolve_project_id, visvoai_home
    return visvoai_home() / "projects" / resolve_project_id(cwd) / "mcp_trust.toml"


def _read_trust(cwd: str) -> dict[str, str]:
    path = _trust_path(cwd)
    if not path.exists():
        return {}
    try:
        return {
            k: v for k, v in (tomllib.loads(path.read_text()).get("trusted") or {}).items()
            if isinstance(v, str)
        }
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def is_trusted(cwd: str, spec: MCPServerSpec) -> bool:
    """Global servers are implicitly trusted; project servers need a recorded
    approval matching the current spec hash."""
    if spec.source == "global":
        return True
    return _read_trust(cwd).get(spec.name) == spec.spec_hash()


def trust_server(cwd: str, spec: MCPServerSpec) -> None:
    """Record approval for a project-defined server (stored outside the repo)."""
    trusted = _read_trust(cwd)
    trusted[spec.name] = spec.spec_hash()
    path = _trust_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[trusted]"] + [f'{name} = "{h}"' for name, h in sorted(trusted.items())]
    path.write_text("\n".join(lines) + "\n")
    invalidate_cache()


def untrusted_servers(cwd: str) -> list[MCPServerSpec]:
    """Enabled project-defined servers awaiting first-use approval."""
    return [
        s for s in load_mcp_servers(cwd).values()
        if s.enabled and not is_trusted(cwd, s)
    ]


# ── Discovery ─────────────────────────────────────────────────────────────────

@dataclass
class MCPServerStatus:
    name: str
    source: str
    transport: str
    state: str                # "connected" | "failed" | "untrusted" | "disabled"
    tool_count: int = 0
    error: Optional[str] = None


def _connection_for(spec: MCPServerSpec) -> dict:
    if spec.command:
        return {
            "transport": "stdio",
            "command": spec.command,
            "args": spec.args,
            # PATH etc. must pass through or the spawned npx/uvx won't resolve.
            "env": {**os.environ, **spec.env},
        }
    return {"transport": "streamable_http", "url": spec.url, "headers": spec.headers or None}


async def _discover_one(spec: MCPServerSpec) -> tuple[MCPServerStatus, list]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({spec.name: _connection_for(spec)})
    try:
        tools = await asyncio.wait_for(
            client.get_tools(server_name=spec.name), timeout=_CONNECT_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        return MCPServerStatus(spec.name, spec.source, spec.transport, "failed",
                               error=f"timed out after {_CONNECT_TIMEOUT_S:.0f}s"), []
    except Exception as e:
        return MCPServerStatus(spec.name, spec.source, spec.transport, "failed",
                               error=str(e) or type(e).__name__), []

    for t in tools:
        t.name = f"{spec.name}__{t.name}"
    return MCPServerStatus(spec.name, spec.source, spec.transport, "connected",
                           tool_count=len(tools)), tools


# Session cache: discovery happens once per project dir, not once per turn
# (the agent graph is rebuilt every turn). /mcp trust and config edits call
# invalidate_cache() to force re-discovery.
_cache: dict[str, tuple[list[MCPServerStatus], list]] = {}


def invalidate_cache() -> None:
    _cache.clear()


async def get_mcp_tools(cwd: str) -> tuple[list[MCPServerStatus], list]:
    """(statuses, langchain_tools) for every configured server — connected once
    per session, independent per-server timeouts, failures reported not raised.
    Untrusted project servers are skipped (state='untrusted') until approved."""
    key = str(Path(cwd).resolve())
    if key in _cache:
        return _cache[key]

    specs = load_mcp_servers(cwd)
    statuses: list[MCPServerStatus] = []
    to_connect: list[MCPServerSpec] = []
    for spec in specs.values():
        if not spec.enabled:
            statuses.append(MCPServerStatus(spec.name, spec.source, spec.transport, "disabled"))
        elif not is_trusted(cwd, spec):
            statuses.append(MCPServerStatus(spec.name, spec.source, spec.transport, "untrusted"))
        else:
            to_connect.append(spec)

    tools: list = []
    if to_connect:
        results = await asyncio.gather(*(_discover_one(s) for s in to_connect))
        for status, server_tools in results:
            statuses.append(status)
            tools.extend(server_tools)

    _cache[key] = (statuses, tools)
    return _cache[key]


# ── Config writing (`visvoai mcp add/remove`) ─────────────────────────────────
# tomllib is read-only and keys._dump_toml is shallow-only, so server tables are
# edited as text blocks: everything outside the `[mcp_servers.<name>]` block —
# comments included — is preserved verbatim.

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_inline_table(d: dict[str, str]) -> str:
    parts = []
    for k, v in d.items():
        key = k if _NAME_RE.match(k) else _toml_str(k)
        parts.append(f"{key} = {_toml_str(v)}")
    return "{ " + ", ".join(parts) + " }"


def render_server_block(name: str, *, command: Optional[str] = None,
                        args: Optional[list[str]] = None,
                        env: Optional[dict[str, str]] = None,
                        url: Optional[str] = None,
                        headers: Optional[dict[str, str]] = None) -> str:
    lines = [f"[{_SECTION}.{name}]"]
    if command:
        lines.append(f"command = {_toml_str(command)}")
        if args:
            lines.append("args = [" + ", ".join(_toml_str(a) for a in args) + "]")
        if env:
            lines.append(f"env = {_toml_inline_table(env)}")
    else:
        lines.append(f"url = {_toml_str(url or '')}")
        if headers:
            lines.append(f"headers = {_toml_inline_table(headers)}")
    return "\n".join(lines) + "\n"


def _block_re(name: str) -> re.Pattern:
    # From the server's table header to the next top-level `[` header (or EOF).
    return re.compile(
        rf"^\[{_SECTION}\.{re.escape(name)}\]\s*\n(?:(?!^\[).*\n?)*",
        re.MULTILINE,
    )


def upsert_server_config(path: Path, name: str, **kwargs) -> None:
    """Add or replace one `[mcp_servers.<name>]` block, leaving the rest of the
    file untouched. Validates the result parses before writing."""
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid server name '{name}' (use letters/digits/-/_)")
    block = render_server_block(name, **kwargs)
    text = path.read_text() if path.exists() else ""
    pattern = _block_re(name)
    if pattern.search(text):
        new = pattern.sub(block, text, count=1)
    else:
        new = text + ("\n" if text and not text.endswith("\n\n") else "") + block
    tomllib.loads(new)  # refuse to write a config the next read would reject
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)
    invalidate_cache()


def remove_server_config(path: Path, name: str) -> bool:
    """Delete a `[mcp_servers.<name>]` block. Returns True if one was removed."""
    if not path.exists():
        return False
    text = path.read_text()
    new, n = _block_re(name).subn("", text)
    if n == 0:
        return False
    path.write_text(new)
    invalidate_cache()
    return True
