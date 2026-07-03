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


def test_creation_format_in_tool_description(tmp_path):
    """The model learns the .md format FROM the tool description — without this
    it invents formats (live incident: an agent wrote a .toml definition that
    the loader silently ignored)."""
    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    assert ".visvoai/agents/<name>.md" in t.description
    assert "frontmatter" in t.description
    assert "NOT toml" in t.description


def test_stray_non_md_files_detected(tmp_path):
    from visvoai.cli.agents import stray_definition_files
    proj = tmp_path / "repo"
    d = proj / ".visvoai" / "agents"
    d.mkdir(parents=True)
    (d / "guardian.toml").write_text("[agent]\nname='guardian'\n")
    (d / "good.md").write_text("A real prompt.")
    (d / ".DS_Store").write_text("")           # dotfiles never flagged

    strays = stray_definition_files(str(proj))
    assert [p.name for p in strays] == ["guardian.toml"]
    roster = load_agent_specs(str(proj))
    assert "good" in roster and "guardian" not in roster


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


def test_least_privilege_and_usage_guidance_in_description(tmp_path):
    """#3/#4: the model is told to pick the smallest tier, that run_agent is
    never a user command, and about the /agents approval step."""
    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    d = t.description
    assert "SMALLEST tools tier" in d
    assert "never a command the user types" in d
    assert "/agents" in d


def _fake_mcp_tool(name="chrome__lighthouse_audit"):
    from langchain_core.tools import StructuredTool

    async def _run(url: str) -> str:
        return "ok"
    return StructuredTool.from_function(coroutine=_run, name=name,
                                        description="fake mcp tool")


def test_mcp_tools_reach_full_tier(tmp_path):
    """#5: session MCP tools join full-tier subagents (gated when approve given)."""
    async def approve(name, args):
        return True

    mcp = [_fake_mcp_tool()]
    names = _names(_tools_for_spec(BUILTIN_AGENTS["general"], str(tmp_path),
                                   approve, extra_tools=mcp))
    assert "chrome__lighthouse_audit" in names
    # ungated path too
    names2 = _names(_tools_for_spec(BUILTIN_AGENTS["general"], str(tmp_path),
                                    None, extra_tools=mcp))
    assert "chrome__lighthouse_audit" in names2


def test_mcp_tools_never_in_read_only(tmp_path):
    names = _names(_tools_for_spec(BUILTIN_AGENTS["explore"], str(tmp_path),
                                   None, extra_tools=[_fake_mcp_tool()]))
    assert "chrome__lighthouse_audit" not in names


def test_mcp_tools_selectable_in_explicit_list(tmp_path):
    spec = AgentSpec(name="x", source="global", description="d", prompt="p",
                     tools="read_file, chrome__lighthouse_audit")
    names = _names(_tools_for_spec(spec, str(tmp_path), None,
                                   extra_tools=[_fake_mcp_tool()]))
    assert names == {"read_file", "chrome__lighthouse_audit"}


@pytest.mark.asyncio
async def test_gated_mcp_tool_in_subagent_prompts(tmp_path):
    """An MCP tool inside a full-tier subagent still hits the approve() gate."""
    calls = []

    async def approve(name, args):
        calls.append(name)
        return False

    tools = _tools_for_spec(BUILTIN_AGENTS["general"], str(tmp_path), approve,
                            extra_tools=[_fake_mcp_tool()])
    mcp = next(t for t in tools if t.name == "chrome__lighthouse_audit")
    out = await mcp.coroutine(url="http://x")
    assert calls == ["chrome__lighthouse_audit"]
    assert "declined" in out


@pytest.mark.asyncio
async def test_pending_agent_surfaced_by_app_not_model(tmp_path, monkeypatch):
    """#2: an untrusted project agent triggers a DETERMINISTIC app warning —
    at startup, and again (new-only diff) at turn end."""
    from visvoai.cli import VisvoApp

    d = tmp_path / ".visvoai" / "agents"
    d.mkdir(parents=True)
    (d / "auditor.md").write_text("You audit.")
    monkeypatch.chdir(tmp_path)

    app = VisvoApp()
    seen = []
    orig = app.notify
    app.notify = lambda msg, **kw: (seen.append(str(msg)), orig(msg, **kw))[1]
    async with app.run_test() as pilot:
        await pilot.pause()
        assert any("auditor" in m and "/agents" in m for m in seen)  # startup

        # Turn-end path: only NEW pending agents notify (no re-nag for 'auditor').
        seen.clear()
        app._notify_pending_agents(before={"auditor"})
        assert seen == []
        (d / "fresh.md").write_text("New one.")
        app._notify_pending_agents(before={"auditor"})
        assert any("fresh" in m for m in seen)
        assert not any("auditor" in m for m in seen)


def test_subagent_tag_helpers():
    from visvoai.cli.agents import SUBAGENT_TAG_PREFIX, subagent_name_from_tags
    assert subagent_name_from_tags([SUBAGENT_TAG_PREFIX + "explore"]) == "explore"
    assert subagent_name_from_tags(["seq:step:1", SUBAGENT_TAG_PREFIX + "x"]) == "x"
    assert subagent_name_from_tags(["other"]) is None
    assert subagent_name_from_tags(None) is None


@pytest.mark.asyncio
async def test_subagent_events_are_tagged_not_leaked(tmp_path, monkeypatch):
    """The leak regression: when the MAIN graph streams a turn that dispatches a
    subagent, every nested (subagent) event must carry the subagent tag so the
    turn worker can filter it — otherwise the subagent's private messages render
    and persist as main-conversation history (live incident: 40 leaked msgs)."""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from visvoai.cli.agents import subagent_name_from_tags
    from visvoai.cli.runtime import CLIRuntime

    class _Fake(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            return self

    # Subagent model: answers immediately (no tool calls).
    import visvoai.ai as vai
    monkeypatch.setattr(vai, "build_chat_model", lambda dep, level=None: _Fake(
        responses=[AIMessage(content="sub answer")]))

    run_agent = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")

    # Main model: first calls run_agent, then finishes.
    main_model = _Fake(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "run_agent", "id": "c1",
            "args": {"agent": "explore", "task": "look around"}}]),
        AIMessage(content="main answer"),
    ])
    graph = CLIRuntime().build_graph(
        model=main_model, core_tools=[run_agent],
        all_tools_map={"run_agent": run_agent}, system_prompt="test")

    main_msg_events, sub_msg_events = [], []
    async for ev in graph.astream_events(
            {"messages": [HumanMessage(content="go")]}, version="v2"):
        if ev.get("event") not in ("on_chat_model_end", "on_tool_start", "on_tool_end"):
            continue
        name = subagent_name_from_tags(ev.get("tags"))
        (sub_msg_events if name else main_msg_events).append(
            (ev["event"], ev.get("name"), name))

    assert any(n == "explore" for _, _, n in sub_msg_events)   # nested events tagged
    # the main stream still sees ITS OWN run_agent tool events, untagged
    assert ("on_tool_start", "run_agent", None) in main_msg_events
    # and no main-classified event is a subagent chat turn
    assert all(e != "on_chat_model_end" or n is None for e, _, n in main_msg_events
               if e == "on_chat_model_end")


@pytest.mark.asyncio
async def test_subagent_gets_context_and_reality_check(tmp_path, monkeypatch):
    """#2 quality: the subagent's system prompt includes the environment (cwd)
    and the tool-reality-check clause, countering stale tool names in
    definitions."""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    seen_system = []

    class _Fake(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages, *a, **kw):
            seen_system.append(str(messages[0].content))
            return await super().ainvoke(messages, *a, **kw)

    import visvoai.ai as vai
    monkeypatch.setattr(vai, "build_chat_model", lambda dep, level=None: _Fake(
        responses=[AIMessage(content="done")]))

    t = build_run_agent_tool(str(tmp_path), "gemini:gemini-3-pro")
    out = await t.coroutine(agent="explore", task="scan")
    assert "done" in out
    system = seen_system[0]
    assert "Tool reality check" in system
    assert str(tmp_path) in system or "Environment" in system   # assembler ran


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
