"""Skills: parsing, roster merge, trust, substitution, read_skill tool, CLI."""
from __future__ import annotations

import pytest

from visvoai.cli import skills
from visvoai.cli.skills import (
    SkillSpec, build_read_skill_tool, is_trusted, load_skill_specs,
    substitute_args, trust_skill, untrusted_skills, write_skill_file,
)


def _make_skill(root, name="release-notes", source_body=None, args=True):
    d = root / name
    d.mkdir(parents=True)
    args_block = "args:\n  version: The version being released\n" if args else ""
    (d / "SKILL.md").write_text(
        f"---\ndescription: Draft release notes\n{args_block}---\n"
        "1. Run `git log $version..HEAD`\n2. See checklist.md for the format.\n"
        if source_body is None else source_body)
    return d


# ── parsing & loading ────────────────────────────────────────────────────────

def test_directory_skill_parses(tmp_path):
    _make_skill(tmp_path / "g")
    specs = skills._load_dir(tmp_path / "g", "global")
    s = specs["release-notes"]
    assert s.description == "Draft release notes"
    assert s.args == {"version": "The version being released"}
    assert "git log $version" in s.body


def test_flat_file_skill_parses(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    (root / "quick-check.md").write_text("---\ndescription: Quick check\n---\nDo X.")
    specs = skills._load_dir(root, "global")
    assert specs["quick-check"].directory is None
    assert specs["quick-check"].body == "Do X."


def test_resources_enumerated_lazily(tmp_path):
    d = _make_skill(tmp_path / "g")
    (d / "checklist.md").write_text("- item")
    (d / "scripts").mkdir()
    (d / "scripts" / "gen.py").write_text("print()")
    (d / "logo.png").write_bytes(b"\x89PNG")          # binary → not served
    specs = skills._load_dir(tmp_path / "g", "global")
    assert specs["release-notes"].resource_names() == ["checklist.md", "scripts/gen.py"]


def test_empty_body_and_missing_entry_skipped(tmp_path):
    root = tmp_path / "g"
    (root / "empty").mkdir(parents=True)
    (root / "empty" / "SKILL.md").write_text("---\ndescription: x\n---\n")
    (root / "no-entry").mkdir()
    (root / "no-entry" / "notes.md").write_text("not a skill")
    assert skills._load_dir(root, "global") == {}


def test_project_overrides_global(tmp_path, monkeypatch):
    g = skills._skills_dir_global()
    _make_skill(g, source_body="---\ndescription: global\n---\nglobal body")
    proj = tmp_path / "repo"
    _make_skill(proj / ".visvoai" / "skills",
                source_body="---\ndescription: project\n---\nproject body")
    roster = load_skill_specs(str(proj))
    assert roster["release-notes"].source == "project"
    assert roster["release-notes"].body == "project body"


# ── trust ────────────────────────────────────────────────────────────────────

def test_project_skill_needs_trust_and_edits_invalidate(tmp_path):
    proj = tmp_path / "repo"
    d = _make_skill(proj / ".visvoai" / "skills")
    spec = load_skill_specs(str(proj))["release-notes"]
    assert not is_trusted(str(proj), spec)
    assert [s.name for s in untrusted_skills(str(proj))] == ["release-notes"]
    trust_skill(str(proj), spec)
    assert is_trusted(str(proj), spec)

    (d / "SKILL.md").write_text("---\ndescription: changed\n---\nnew body")
    changed = load_skill_specs(str(proj))["release-notes"]
    assert not is_trusted(str(proj), changed)     # any body change re-prompts


def test_new_resource_file_invalidates_trust(tmp_path):
    """Resources are hashed by NAME: adding one changes the surface."""
    proj = tmp_path / "repo"
    d = _make_skill(proj / ".visvoai" / "skills")
    spec = load_skill_specs(str(proj))["release-notes"]
    trust_skill(str(proj), spec)
    (d / "new-ref.md").write_text("more instructions")
    assert not is_trusted(str(proj), load_skill_specs(str(proj))["release-notes"])


def test_global_implicitly_trusted(tmp_path):
    s = SkillSpec(name="mine", source="global", description="d", body="b")
    assert is_trusted(str(tmp_path), s)


# ── substitution ─────────────────────────────────────────────────────────────

def test_substitution_rules():
    declared = {"version": "d", "focus": "d"}
    body = "Release $version. Focus: $focus. Shell: echo $HOME. All:\n$ARGUMENTS"
    out = substitute_args(body, declared, {"version": "1.2.0"})
    assert "Release 1.2.0." in out
    assert "Focus: ." in out                      # declared, not given → empty
    assert "echo $HOME" in out                    # undeclared → untouched
    assert "version: 1.2.0" in out                # $ARGUMENTS block


# ── read_skill tool ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_skill_body_resources_and_errors(tmp_path, monkeypatch):
    proj = tmp_path / "repo"
    d = _make_skill(proj / ".visvoai" / "skills")
    (d / "checklist.md").write_text("- keep it short")
    spec = load_skill_specs(str(proj))["release-notes"]
    trust_skill(str(proj), spec)

    t = build_read_skill_tool(str(proj))
    assert "release-notes: Draft release notes" in t.description
    assert "$version" in t.description

    body = await t.coroutine(skill="release-notes", args={"version": "2.0"})
    assert "git log 2.0..HEAD" in body            # substituted
    assert "checklist.md" in body                 # resources advertised

    res = await t.coroutine(skill="release-notes", resource="checklist.md")
    assert "- keep it short" in res

    assert (await t.coroutine(skill="release-notes",
                              resource="nope.md")).startswith("ERROR")
    assert (await t.coroutine(skill="ghost", args=None)).startswith("ERROR")


@pytest.mark.asyncio
async def test_untrusted_project_skills_excluded(tmp_path):
    proj = tmp_path / "repo"
    _make_skill(proj / ".visvoai" / "skills")
    t = build_read_skill_tool(str(proj))
    assert "release-notes" not in t.description
    out = await t.coroutine(skill="release-notes")
    assert out.startswith("ERROR: unknown skill")


def test_write_skill_file_roundtrip(tmp_path):
    path = write_skill_file(tmp_path, "notes", description="Take notes",
                            args={"topic": "What about"}, body="Write $topic.")
    specs = skills._load_dir(tmp_path, "global")
    s = specs["notes"]
    assert s.description == "Take notes" and s.args == {"topic": "What about"}
    assert path.name == "SKILL.md"


# ── graph wiring ─────────────────────────────────────────────────────────────

def test_read_skill_in_main_graph_and_all_subagent_tiers(tmp_path, monkeypatch):
    from visvoai.cli.agents import BUILTIN_AGENTS, _tools_for_spec

    names_ro = {t.name for t in _tools_for_spec(
        BUILTIN_AGENTS["explore"], str(tmp_path), None)}
    names_full = {t.name for t in _tools_for_spec(
        BUILTIN_AGENTS["general"], str(tmp_path), None)}
    assert "read_skill" in names_ro and "read_skill" in names_full

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
    assert "read_skill" in captured["names"]


def test_global_layer_never_doubles_as_project_layer(tmp_path, monkeypatch):
    """Outside a project, project_root() walks up to $HOME (the global
    ~/.visvoai/config.toml matches its anchor) — the project layer must be
    SKIPPED then, or global skills reload as 'project' and demand trust."""
    home = skills._skills_dir_global().parent          # the fake VISVOAI_HOME
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text("")              # the anchor that misleads
    _make_skill(skills._skills_dir_global())
    monkeypatch.setattr("visvoai.cli.store.project_root", lambda cwd: home)

    roster = load_skill_specs(str(tmp_path))
    assert roster["release-notes"].source == "global"
    assert untrusted_skills(str(tmp_path)) == []       # implicitly trusted

    # same guard for agents
    from visvoai.cli import agents as agents_mod
    ag = agents_mod._agents_dir_global()
    ag.mkdir(parents=True, exist_ok=True)
    (ag / "helper.md").write_text("A prompt.")
    aroster = agents_mod.load_agent_specs(str(tmp_path))
    assert aroster["helper"].source == "global"


# ── `visvoai skills` commands ────────────────────────────────────────────────

def test_cli_skills_list_show_remove(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from visvoai.cli.main import cli

    g = skills._skills_dir_global()
    _make_skill(g)
    r = CliRunner().invoke(cli, ["skills", "list", "--cwd", str(tmp_path)])
    assert r.exit_code == 0 and "release-notes" in r.output

    r2 = CliRunner().invoke(cli, ["skills", "show", "release-notes",
                                  "--cwd", str(tmp_path)])
    assert r2.exit_code == 0 and "instructions" in r2.output

    r3 = CliRunner().invoke(cli, ["skills", "remove", "release-notes",
                                  "--cwd", str(tmp_path)])
    assert r3.exit_code == 0
    assert "release-notes" not in load_skill_specs(str(tmp_path))


# ── pending-trust surfacing covers skills too ────────────────────────────────

@pytest.mark.asyncio
async def test_pending_skill_surfaced_by_app(tmp_path, monkeypatch):
    from visvoai.cli import VisvoApp

    _make_skill(tmp_path / ".visvoai" / "skills")
    monkeypatch.chdir(tmp_path)
    app = VisvoApp()
    seen = []
    orig = app.notify
    app.notify = lambda msg, **kw: (seen.append(str(msg)), orig(msg, **kw))[1]
    async with app.run_test() as pilot:
        await pilot.pause()
        assert any("release-notes" in m and "/skills" in m for m in seen)
