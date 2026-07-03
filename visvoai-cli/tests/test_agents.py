"""Agents: definition parsing, roster merge, trust, tool tiers, run_agent."""
from __future__ import annotations

import pytest

from visvoai.cli import agents
from visvoai.cli.agents import (
    BUILTIN_AGENTS, AgentSpec, build_run_agent_tool, load_agent_specs,
    is_trusted, trust_agent, untrusted_agents, write_agent_file,
    _parse_agent_file, _tools_for_spec,
)


# ── Definition files ─────────────────────────────────────────────────────────

def test_parse_full_frontmatter(tmp_path):
    p = tmp_path / "reviewer.md"
    p.write_text("---\ndescription: Reviews diffs\ntools: read-only\n"
                 "model: gemini:gemini-3.1-flash\n---\nYou review code.\n")
    spec = _parse_agent_file(p, "global")
    assert spec.name == "reviewer"
    assert spec.description == "Reviews diffs"
    assert spec.tools == "read-only"
    assert spec.model == "gemini:gemini-3.1-flash"
    assert spec.prompt == "You review code."


def test_parse_no_frontmatter_defaults(tmp_path):
    p = tmp_path / "helper.md"
    p.write_text("Just a prompt body.\n")
    spec = _parse_agent_file(p, "project")
    assert spec.tools == "read-only"          # safe default
    assert spec.model is None
    assert spec.prompt == "Just a prompt body."


def test_parse_rejects_empty_body(tmp_path):
    p = tmp_path / "empty.md"
    p.write_text("---\ndescription: x\n---\n\n")
    assert _parse_agent_file(p, "global") is None


def test_parse_rejects_bad_name(tmp_path):
    p = tmp_path / ".hidden.md"
    p.write_text("prompt")
    assert _parse_agent_file(p, "global") is None


def test_write_agent_file_roundtrip(tmp_path):
    path = write_agent_file(tmp_path, "docs-bot", description="Writes docs",
                            tools="full", model=None, prompt="You write docs.")
    spec = _parse_agent_file(path, "global")
    assert (spec.description, spec.tools, spec.model) == ("Writes docs", "full", None)
    assert spec.prompt == "You write docs."


def test_write_refuses_builtin_shadow(tmp_path):
    with pytest.raises(ValueError):
        write_agent_file(tmp_path, "explore", description="x", tools="full",
                         model=None, prompt="p")


# ── Roster merge ─────────────────────────────────────────────────────────────

def test_builtins_always_present(tmp_path):
    roster = load_agent_specs(str(tmp_path))
    assert {"explore", "general"} <= set(roster)
    assert roster["explore"].tools == "read-only"
    assert roster["general"].tools == "full"


def test_project_overrides_global(tmp_path, monkeypatch):
    home_agents = agents._agents_dir_global()
    home_agents.mkdir(parents=True, exist_ok=True)
    (home_agents / "reviewer.md").write_text("global reviewer prompt")
    proj = tmp_path / "repo"
    proj_agents = proj / ".visvoai" / "agents"
    proj_agents.mkdir(parents=True)
    (proj_agents / "reviewer.md").write_text("project reviewer prompt")

    roster = load_agent_specs(str(proj))
    assert roster["reviewer"].source == "project"
    assert roster["reviewer"].prompt == "project reviewer prompt"


# ── Trust ────────────────────────────────────────────────────────────────────

def _project_with_agent(tmp_path, body="You audit.\n"):
    proj = tmp_path / "repo"
    d = proj / ".visvoai" / "agents"
    d.mkdir(parents=True)
    (d / "auditor.md").write_text(body)
    return proj


def test_project_agent_needs_trust(tmp_path):
    proj = _project_with_agent(tmp_path)
    spec = load_agent_specs(str(proj))["auditor"]
    assert not is_trusted(str(proj), spec)
    assert [s.name for s in untrusted_agents(str(proj))] == ["auditor"]

    trust_agent(str(proj), spec)
    assert is_trusted(str(proj), spec)
    assert untrusted_agents(str(proj)) == []


def test_trust_invalidated_by_definition_change(tmp_path):
    proj = _project_with_agent(tmp_path)
    spec = load_agent_specs(str(proj))["auditor"]
    trust_agent(str(proj), spec)

    (proj / ".visvoai" / "agents" / "auditor.md").write_text(
        "---\ntools: full\n---\nNow with edits.\n")
    changed = load_agent_specs(str(proj))["auditor"]
    assert not is_trusted(str(proj), changed)   # any change re-prompts


def test_builtin_and_global_implicitly_trusted(tmp_path):
    assert is_trusted(str(tmp_path), BUILTIN_AGENTS["explore"])
    g = AgentSpec(name="mine", source="global", description="d", prompt="p")
    assert is_trusted(str(tmp_path), g)


# ── Tool tiers ───────────────────────────────────────────────────────────────

def _names(tools):
    return {t.name for t in tools}


def test_read_only_tier_has_no_mutators(tmp_path):
    spec = BUILTIN_AGENTS["explore"]
    names = _names(_tools_for_spec(spec, str(tmp_path), approve=None))
    assert "run_shell" in names and "read_file" in names
    assert not names & {"edit_file", "write_file", "run_agent"}


def test_full_tier_has_everything_but_run_agent(tmp_path):
    async def approve(name, args):
        return True
    names = _names(_tools_for_spec(BUILTIN_AGENTS["general"], str(tmp_path), approve))
    assert {"edit_file", "write_file", "run_shell", "read_file"} <= names
    assert "run_agent" not in names            # depth cap


def test_explicit_tool_list_filters(tmp_path):
    spec = AgentSpec(name="x", source="global", description="d", prompt="p",
                     tools="read_file, web_search, run_agent")
    names = _names(_tools_for_spec(spec, str(tmp_path), approve=None))
    assert names == {"read_file", "web_search"}   # run_agent stripped


@pytest.mark.asyncio
async def test_readonly_shell_refuses_writes(tmp_path):
    from visvoai.cli.gated_tools import build_readonly_shell
    shell = build_readonly_shell()
    out = await shell.coroutine(command=f"touch {tmp_path}/x")
    assert "read-only" in out and "[exit: -1]" in out
    assert not (tmp_path / "x").exists()
    ok = await shell.coroutine(command=f"ls {tmp_path}")
    assert "[exit: 0]" in ok


# ── run_agent tool ───────────────────────────────────────────────────────────

def test_roster_in_tool_description(tmp_path):
    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    assert "explore:" in t.description and "general:" in t.description
    assert "PARALLEL" in t.description.upper()


def test_untrusted_project_agents_excluded(tmp_path):
    proj = _project_with_agent(tmp_path)
    t = build_run_agent_tool(str(proj), "gemini:gemini-3-pro")
    assert "auditor" not in t.description
    trust_agent(str(proj), load_agent_specs(str(proj))["auditor"])
    t2 = build_run_agent_tool(str(proj), "gemini:gemini-3-pro")
    assert "auditor" in t2.description


@pytest.mark.asyncio
async def test_run_agent_unknown_and_empty(tmp_path):
    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    out = await t.coroutine(agent="nope", task="do a thing")
    assert out.startswith("ERROR: unknown agent")
    assert "explore" in out                    # tells the model what exists
    out2 = await t.coroutine(agent="explore", task="   ")
    assert out2.startswith("ERROR: empty task")


@pytest.mark.asyncio
async def test_run_agent_dispatches_subgraph(tmp_path, monkeypatch):
    """Full dispatch through a stubbed model: the subagent graph runs, and the
    final AI text comes back with the agent trailer."""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class _Fake(FakeMessagesListChatModel):
        def bind_tools(self, tools):     # fake model can't bind; loop still runs
            return self

    fake = _Fake(responses=[AIMessage(content="Found it: src/x.py:12")])
    import visvoai.ai as vai
    monkeypatch.setattr(vai, "build_chat_model", lambda dep, level=None: fake)

    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    out = await t.coroutine(agent="explore", task="find x")
    assert "Found it: src/x.py:12" in out
    assert "[agent: explore" in out


# ── `visvoai agents` commands ────────────────────────────────────────────────

def test_cli_agents_list_and_show(tmp_path):
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    r = CliRunner().invoke(cli, ["agents", "list", "--cwd", str(tmp_path)])
    assert r.exit_code == 0
    assert "explore" in r.output and "general" in r.output

    r2 = CliRunner().invoke(cli, ["agents", "show", "explore", "--cwd", str(tmp_path)])
    assert r2.exit_code == 0
    assert "read-only" in r2.output and "system prompt" in r2.output

    r3 = CliRunner().invoke(cli, ["agents", "remove", "explore"])
    assert r3.exit_code == 1 and "built-in" in r3.output


def test_run_agent_wired_into_graph_tools(tmp_path, monkeypatch):
    """build_agent_graph(enable_agents=True) exposes run_agent to the model."""
    captured = {}

    class _RT:
        def __init__(self, assembler=None):
            pass

        def build_graph(self, model, core_tools, all_tools_map, system_prompt):
            captured["names"] = set(all_tools_map)
            return object()

    from visvoai.cli import agent as agent_mod
    import visvoai.ai as vai
    import visvoai.cli.runtime as rt
    monkeypatch.setattr(vai, "build_chat_model", lambda dep, level=None: object())
    monkeypatch.setattr(rt, "CLIRuntime", _RT)
    agent_mod.build_agent_graph("gemini:gemini-3-pro", str(tmp_path))
    assert "run_agent" in captured["names"]

    captured.clear()
    agent_mod.build_agent_graph("gemini:gemini-3-pro", str(tmp_path),
                                enable_agents=False)
    assert "run_agent" not in captured["names"]
