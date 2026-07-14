"""toolkit: make_cli_tool contract, declared gates, global .py plugin loader."""
from __future__ import annotations

import pytest

from visvoai.cli.toolkit import (
    apply_gates, load_user_tools, make_cli_tool, user_tools_dir,
)


def _greet(name: str, excited: bool = False) -> str:
    """Greet someone by name."""
    return f"hello {name}" + ("!" if excited else "")


def test_make_cli_tool_schema_description_and_run():
    t = make_cli_tool(_greet, gate=None)
    assert t.name == "_greet" or t.name == "_greet"  # name from fn
    assert "Greet someone" in t.description
    props = t.args_schema.model_json_schema()["properties"]
    assert set(props) == {"name", "excited"}
    assert t.invoke({"name": "aj"}) == "hello aj"
    assert (t.metadata or {}).get("gate") is None


def test_errors_become_data_and_output_capped():
    def boom(x: str) -> str:
        """Boom."""
        raise RuntimeError("nope")

    def flood() -> str:
        """Flood."""
        return "\n".join(str(i) for i in range(50))

    assert make_cli_tool(boom, gate=None).invoke({"x": "a"}).startswith("ERROR: nope")
    out = make_cli_tool(flood, gate=None, cap=10).invoke({})
    assert "truncated" in out and out.count("\n") <= 11


@pytest.mark.asyncio
async def test_async_fn_and_declared_approve_gate():
    async def deploy(env: str) -> str:
        """Deploy to an environment."""
        return f"deployed {env}"

    calls = []

    async def approve(name, args):
        calls.append((name, args))
        return True

    t = make_cli_tool(deploy, gate="approve")
    gated = apply_gates([t], approve)[0]
    out = await gated.coroutine(env="prod")
    assert out == "deployed prod"
    assert calls and calls[0][0] == "deploy"
    # ungated mode (approve=None) → passes through
    assert apply_gates([t], None)[0] is t


def test_plugin_loader_roundtrip(tmp_path):
    d = user_tools_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "mytools.py").write_text(
        "from visvoai.cli.toolkit import make_cli_tool\n"
        "def add(a: int, b: int) -> str:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    return str(a + b)\n"
        "TOOLS = [make_cli_tool(add, gate=None)]\n")
    (d / "broken.py").write_text("raise RuntimeError('bad plugin')\n")
    (d / "no_tools.py").write_text("x = 1\n")

    tools = load_user_tools()   # broken/no-TOOLS files skipped, never raise
    names = {t.name for t in tools}
    assert names == {"add"}
    assert tools[0].invoke({"a": 2, "b": 3}) == "5"


def test_plugin_tools_reach_the_graph(tmp_path, monkeypatch):
    d = user_tools_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "t.py").write_text(
        "from visvoai.cli.toolkit import make_cli_tool\n"
        "def ping() -> str:\n"
        "    \"\"\"Ping.\"\"\"\n"
        "    return 'pong'\n"
        "TOOLS = [make_cli_tool(ping, gate=None)]\n")

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
    assert "ping" in captured["names"]
