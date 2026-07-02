"""Tests for visvoai.cli.mcp — config merge, ${VAR} expansion, trust, discovery."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from visvoai.cli import mcp


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Isolated VISVOAI_HOME + project dir with .visvoai anchors."""
    home = tmp_path / "home"
    project = tmp_path / "proj"
    (home).mkdir()
    (project / ".visvoai").mkdir(parents=True)
    monkeypatch.setenv("VISVOAI_HOME", str(home))
    mcp.invalidate_cache()
    yield home, project
    mcp.invalidate_cache()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# ── Config loading & merge ────────────────────────────────────────────────────

def test_no_config_no_servers(isolated):
    home, project = isolated
    assert mcp.load_mcp_servers(str(project)) == {}


def test_global_and_project_merge_project_wins(isolated):
    home, project = isolated
    _write(home / "config.toml", """
[mcp_servers.github]
command = "npx"
args = ["-y", "server-github"]

[mcp_servers.shared]
url = "https://global.example/mcp"
""")
    _write(project / ".visvoai" / "config.toml", """
project_id = "p1"

[mcp_servers.linear]
url = "https://mcp.linear.app/mcp"

[mcp_servers.shared]
url = "https://project.example/mcp"
""")
    servers = mcp.load_mcp_servers(str(project))
    assert set(servers) == {"github", "linear", "shared"}
    assert servers["github"].source == "global"
    assert servers["github"].transport == "stdio"
    assert servers["linear"].source == "project"
    assert servers["linear"].transport == "streamable_http"
    assert servers["shared"].url == "https://project.example/mcp"  # project wins
    assert servers["shared"].source == "project"


def test_env_expansion_in_headers_and_env(isolated, monkeypatch):
    home, project = isolated
    monkeypatch.setenv("MY_TOKEN", "sekret")
    _write(home / "config.toml", """
[mcp_servers.a]
url = "https://x/mcp"
headers = { Authorization = "Bearer ${MY_TOKEN}" }

[mcp_servers.b]
command = "npx"
env = { TOKEN = "${MY_TOKEN}", MISSING = "${NOPE_NOT_SET}" }
""")
    servers = mcp.load_mcp_servers(str(project))
    assert servers["a"].headers["Authorization"] == "Bearer sekret"
    assert servers["b"].env["TOKEN"] == "sekret"
    assert servers["b"].env["MISSING"] == ""  # missing var → empty, not literal


def test_invalid_entries_skipped(isolated):
    home, project = isolated
    _write(home / "config.toml", """
[mcp_servers.nothing]
enabled = true

[mcp_servers.ok]
url = "https://x/mcp"
""")
    servers = mcp.load_mcp_servers(str(project))
    assert set(servers) == {"ok"}   # no command/url → skipped


# ── Trust ─────────────────────────────────────────────────────────────────────

def test_global_servers_implicitly_trusted(isolated):
    home, project = isolated
    spec = mcp.MCPServerSpec(name="g", source="global", command="npx")
    assert mcp.is_trusted(str(project), spec)


def test_project_server_untrusted_until_recorded(isolated):
    home, project = isolated
    spec = mcp.MCPServerSpec(name="p", source="project", command="npx", args=["x"])
    assert not mcp.is_trusted(str(project), spec)
    mcp.trust_server(str(project), spec)
    assert mcp.is_trusted(str(project), spec)


def test_spec_change_invalidates_trust(isolated):
    home, project = isolated
    spec = mcp.MCPServerSpec(name="p", source="project", command="npx", args=["a"])
    mcp.trust_server(str(project), spec)
    changed = mcp.MCPServerSpec(name="p", source="project", command="npx", args=["b"])
    assert not mcp.is_trusted(str(project), changed)


def test_token_rotation_does_not_invalidate_trust(isolated):
    home, project = isolated
    s1 = mcp.MCPServerSpec(name="p", source="project", url="https://x/mcp",
                           headers={"Authorization": "Bearer old"})
    mcp.trust_server(str(project), s1)
    s2 = mcp.MCPServerSpec(name="p", source="project", url="https://x/mcp",
                           headers={"Authorization": "Bearer new"})
    assert mcp.is_trusted(str(project), s2)      # values excluded from hash
    s3 = mcp.MCPServerSpec(name="p", source="project", url="https://x/mcp",
                           headers={"X-Other": "v"})
    assert not mcp.is_trusted(str(project), s3)  # header NAME change re-prompts


def test_untrusted_servers_lists_only_enabled_project(isolated):
    home, project = isolated
    _write(project / ".visvoai" / "config.toml", """
project_id = "p1"

[mcp_servers.a]
url = "https://a/mcp"

[mcp_servers.b]
url = "https://b/mcp"
enabled = false
""")
    names = [s.name for s in mcp.untrusted_servers(str(project))]
    assert names == ["a"]


# ── Discovery (mocked transport) ──────────────────────────────────────────────

def test_get_mcp_tools_states_and_cache(isolated, monkeypatch):
    home, project = isolated
    _write(home / "config.toml", """
[mcp_servers.up]
url = "https://up/mcp"

[mcp_servers.down]
url = "https://down/mcp"

[mcp_servers.off]
url = "https://off/mcp"
enabled = false
""")
    _write(project / ".visvoai" / "config.toml", """
project_id = "p1"

[mcp_servers.repo]
command = "npx"
""")

    class FakeTool:
        def __init__(self, name): self.name = name

    calls = []

    async def fake_discover(spec, stack):
        calls.append(spec.name)
        if spec.name == "down":
            return mcp.MCPServerStatus(spec.name, spec.source, spec.transport,
                                       "failed", error="boom"), []
        return mcp.MCPServerStatus(spec.name, spec.source, spec.transport,
                                   "connected", tool_count=2), \
               [FakeTool(f"{spec.name}__t1"), FakeTool(f"{spec.name}__t2")]

    monkeypatch.setattr(mcp, "_discover_one", fake_discover)

    statuses, tools = asyncio.run(mcp.get_mcp_tools(str(project)))
    by_name = {s.name: s.state for s in statuses}
    assert by_name == {"up": "connected", "down": "failed",
                       "off": "disabled", "repo": "untrusted"}
    assert [t.name for t in tools] == ["up__t1", "up__t2"]
    assert sorted(calls) == ["down", "up"]       # untrusted/disabled never connect

    # Cached: second call does not re-discover.
    asyncio.run(mcp.get_mcp_tools(str(project)))
    assert sorted(calls) == ["down", "up"]

    # Trusting the project server invalidates the cache → re-discovers both.
    repo_spec = mcp.load_mcp_servers(str(project))["repo"]
    mcp.trust_server(str(project), repo_spec)
    statuses2, tools2 = asyncio.run(mcp.get_mcp_tools(str(project)))
    assert {s.name: s.state for s in statuses2}["repo"] == "connected"
    assert len(tools2) == 4


# ── gate_tool ─────────────────────────────────────────────────────────────────

def test_gate_tool_copy_denies_and_allows():
    from langchain_core.tools import StructuredTool
    from visvoai.cli.gated_tools import gate_tool, _DENIED

    async def hello(x: int) -> str:
        """say hello"""
        return f"hi {x}"

    t = StructuredTool.from_function(coroutine=hello, name="srv__hello", description="d")
    decisions = []

    async def approve(name, args):
        decisions.append((name, args))
        return len(decisions) > 1   # deny first, allow after

    gated = gate_tool(t, approve)
    assert gated is not t                      # copy, not mutation
    assert t.coroutine is hello                # original untouched (cache-safe)
    assert gated.name == "srv__hello"

    assert asyncio.run(gated.coroutine(x=1)) == _DENIED
    assert asyncio.run(gated.coroutine(x=2)) == "hi 2"
    assert decisions == [("srv__hello", {"x": 1}), ("srv__hello", {"x": 2})]

    # Re-gating the ORIGINAL again (per-turn rebuild) must not stack prompts.
    gated2 = gate_tool(t, approve)
    assert asyncio.run(gated2.coroutine(x=3)) == "hi 3"
    assert len(decisions) == 3                 # exactly one approve per call


# ── Config writing (upsert/remove) ────────────────────────────────────────────

def test_upsert_appends_and_replaces_preserving_rest(isolated):
    home, project = isolated
    cfg = home / "config.toml"
    _write(cfg, '# my comment\n[api_keys]\ngemini = "k"\n')

    mcp.upsert_server_config(cfg, "github", command="npx",
                             args=["-y", "server-github"],
                             env={"TOKEN": "${GH}"})
    servers = mcp.load_mcp_servers(str(project))
    assert servers["github"].command == "npx"
    assert "# my comment" in cfg.read_text()          # untouched content survives
    assert '[api_keys]' in cfg.read_text()

    # Replace in place — no duplicate blocks.
    mcp.upsert_server_config(cfg, "github", url="https://gh/mcp")
    text = cfg.read_text()
    assert text.count("[mcp_servers.github]") == 1
    assert mcp.load_mcp_servers(str(project))["github"].transport == "streamable_http"


def test_upsert_rejects_bad_name(isolated):
    home, project = isolated
    with pytest.raises(ValueError):
        mcp.upsert_server_config(home / "config.toml", "bad name!", url="https://x")


def test_remove_server_config(isolated):
    home, project = isolated
    cfg = home / "config.toml"
    mcp.upsert_server_config(cfg, "a", url="https://a/mcp")
    mcp.upsert_server_config(cfg, "b", url="https://b/mcp")
    assert mcp.remove_server_config(cfg, "a")
    assert set(mcp.load_mcp_servers(str(project))) == {"b"}
    assert not mcp.remove_server_config(cfg, "nope")


def test_rendered_block_escapes_quotes(isolated):
    home, project = isolated
    cfg = home / "config.toml"
    mcp.upsert_server_config(cfg, "q", command="sh",
                             args=['-c', 'echo "hi"'])
    assert mcp.load_mcp_servers(str(project))["q"].args == ["-c", 'echo "hi"']


# ── `visvoai mcp …` subcommands & default-group dispatch ─────────────────────

def test_cli_mcp_add_list_remove(isolated, monkeypatch):
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    home, project = isolated
    runner = CliRunner()

    r = runner.invoke(cli, ["mcp", "add", "everything", "--",
                            "npx", "-y", "@modelcontextprotocol/server-everything"])
    assert r.exit_code == 0, r.output
    assert "Added MCP server 'everything'" in r.output

    r = runner.invoke(cli, ["mcp", "add", "linear", "--url", "https://mcp.linear.app/mcp",
                            "--header", "Authorization=Bearer ${LINEAR_API_KEY}"])
    assert r.exit_code == 0, r.output

    r = runner.invoke(cli, ["mcp", "list", "--cwd", str(project)])
    assert r.exit_code == 0
    assert "everything" in r.output and "linear" in r.output
    assert "stdio" in r.output and "streamable_http" in r.output

    r = runner.invoke(cli, ["mcp", "remove", "everything", "--cwd", str(project)])
    assert r.exit_code == 0
    r = runner.invoke(cli, ["mcp", "list", "--cwd", str(project)])
    assert "everything" not in r.output

    r = runner.invoke(cli, ["mcp", "remove", "ghost", "--cwd", str(project)])
    assert r.exit_code == 1


def test_cli_mcp_add_validation(isolated):
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    runner = CliRunner()
    # neither command nor url
    assert runner.invoke(cli, ["mcp", "add", "x"]).exit_code != 0
    # both
    assert runner.invoke(cli, ["mcp", "add", "x", "--url", "https://u", "--",
                               "npx"]).exit_code != 0
    # header on a command server
    assert runner.invoke(cli, ["mcp", "add", "x", "--header", "A=b", "--",
                               "npx"]).exit_code != 0


def test_cli_mcp_add_raw_secret_warning(isolated):
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    runner = CliRunner()
    r = runner.invoke(cli, ["mcp", "add", "x", "--url", "https://u",
                            "--header", "Authorization=Bearer abc123realtoken"])
    assert r.exit_code == 0
    assert "raw secret" in r.output


def test_default_group_routes_prompt_to_chat(isolated, monkeypatch):
    from click.testing import CliRunner
    import visvoai.cli.main as main

    calls = {}
    async def fake_single_shot(prompt, model, cwd, verbose, assume_yes=False):
        calls["prompt"] = prompt
    monkeypatch.setattr(main, "_run_single_shot", fake_single_shot)
    monkeypatch.setattr(main, "_launch_tui", lambda *a: calls.setdefault("tui", True))

    runner = CliRunner()
    assert runner.invoke(main.cli, ["fix", "the", "bug"]).exit_code == 0
    assert calls["prompt"] == "fix the bug"

    assert runner.invoke(main.cli, []).exit_code == 0
    assert calls.get("tui") is True

    # options-first still routes to chat
    calls.clear()
    assert runner.invoke(main.cli, ["--verbose", "hello"]).exit_code == 0
    assert calls["prompt"] == "hello"


def test_version_flag_not_routed_to_chat():
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    r = CliRunner().invoke(cli, ["--version"])
    assert r.exit_code == 0
    assert "visvoai-cli v" in r.output


# ── MCPScreen renders (pilot) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_screen_renders_and_trust_toggles(isolated):
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens.mcp_view import MCPScreen, ServerRow

    statuses = [
        mcp.MCPServerStatus("everything", "global", "stdio", "connected", tool_count=13),
        mcp.MCPServerStatus("broken", "global", "streamable_http", "failed",
                            error="401 Unauthorized"),
        mcp.MCPServerStatus("repo-tools", "project", "stdio", "untrusted"),
    ]
    specs = {
        "everything": mcp.MCPServerSpec(name="everything", source="global",
                                        command="npx", args=["-y", "server-everything"]),
        "repo-tools": mcp.MCPServerSpec(name="repo-tools", source="project",
                                        command="npx", args=["-y", "repo-tools"]),
    }
    tools = {"everything": [f"everything__t{i}" for i in range(13)]}

    app = VisvoApp()
    async with app.run_test() as pilot:
        screen = MCPScreen(statuses, specs, tools)
        results = []
        app.push_screen(screen, results.append)
        await pilot.pause()

        rows = list(screen.query(ServerRow))
        assert [r.status.name for r in rows] == ["repo-tools", "broken", "everything"]
        assert "13 tools" in screen._summary()
        assert "1 awaiting your approval" in screen._summary()

        # enter on the untrusted row (sorted first) marks it pending
        await pilot.press("enter")
        assert rows[0].pending_trust is True
        # esc dismisses with the trust list
        await pilot.press("escape")
        await pilot.pause()
        assert results == [["repo-tools"]]


@pytest.mark.asyncio
async def test_mcp_screen_empty_state_renders(isolated):
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens.mcp_view import MCPScreen

    app = VisvoApp()
    async with app.run_test() as pilot:
        screen = MCPScreen([], {})
        app.push_screen(screen)
        await pilot.pause()
        empty = screen.query_one("#mcp-empty")
        text = str(empty.render())
        assert "visvoai mcp add chrome" in text
        assert "[mcp_servers.github]" in text
        assert "Ask the agent" in text


@pytest.mark.asyncio
async def test_mcp_screen_shows_add_help_with_servers_present(isolated):
    from visvoai.cli import VisvoApp
    from visvoai.cli.screens.mcp_view import MCPScreen

    statuses = [mcp.MCPServerStatus("x", "global", "stdio", "connected", tool_count=1)]
    app = VisvoApp()
    async with app.run_test() as pilot:
        screen = MCPScreen(statuses, {})
        app.push_screen(screen)
        await pilot.pause()
        text = str(screen.query_one("#mcp-add").render())
        assert "visvoai mcp add" in text
        assert "ask the agent" in text
