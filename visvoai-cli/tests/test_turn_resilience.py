"""Turn resilience: shell-timeout as a tool error, error classification, and the
replayable-suffix trim that lets an errored turn still persist."""
from __future__ import annotations

import subprocess

from langchain_core.messages import AIMessage, ToolMessage

from visvoai.cli.agent_turn import _classify_turn_error, _sanitize_thread
from visvoai.cli.tools import build_cli_tools


def _tc(id):
    return {"name": "run_shell", "args": {}, "id": id, "type": "tool_call"}


# ---- #6: shell timeout is a TOOL error (returned as data), never a raise ----

def test_run_shell_timeout_returns_error_not_raise(monkeypatch):
    import visvoai.cli.tools.shell as sh

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=30)

    monkeypatch.setattr(sh.subprocess, "run", boom)
    run_shell = {t.name: t for t in build_cli_tools(cwd=".")}["run_shell"]
    out = run_shell.invoke({"command": "sleep 99"})
    assert "timed out" in out.lower()
    assert "[exit: -1]" in out          # UI parses this as a failed tool node


def test_run_shell_timeout_keeps_partial_output(monkeypatch):
    import visvoai.cli.tools.shell as sh

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=30, output="line1\nline2")

    monkeypatch.setattr(sh.subprocess, "run", boom)
    run_shell = {t.name: t for t in build_cli_tools(cwd=".")}["run_shell"]
    out = run_shell.invoke({"command": "x"})
    assert "line1" in out and "timed out" in out.lower()


# ---- Q1: agent-settable, bounded timeout ----

def test_run_shell_custom_timeout_passed_through(monkeypatch):
    import visvoai.cli.tools.shell as sh
    seen = {}

    def fake_run(*a, **k):
        seen["timeout"] = k.get("timeout")
        raise subprocess.TimeoutExpired(cmd="x", timeout=k.get("timeout"))

    monkeypatch.setattr(sh.subprocess, "run", fake_run)
    run_shell = {t.name: t for t in build_cli_tools(cwd=".")}["run_shell"]
    run_shell.invoke({"command": "build", "timeout_seconds": 120})
    assert seen["timeout"] == 120


def test_run_shell_timeout_clamped_to_max(monkeypatch):
    import visvoai.cli.tools.shell as sh
    seen = {}

    def fake_run(*a, **k):
        seen["timeout"] = k.get("timeout")
        raise subprocess.TimeoutExpired(cmd="x", timeout=k.get("timeout"))

    monkeypatch.setattr(sh.subprocess, "run", fake_run)
    run_shell = {t.name: t for t in build_cli_tools(cwd=".")}["run_shell"]
    run_shell.invoke({"command": "x", "timeout_seconds": 99999})
    assert seen["timeout"] == sh.SHELL_TIMEOUT_MAX


# ---- #4: error classification → ErrorBlock kind + message ----

def test_classify_auth_error():
    kind, msg, _ = _classify_turn_error(Exception("Error code: 401 - {'message': 'User not found'}"))
    assert kind == "model" and "key" in msg.lower()


def test_classify_network_error():
    kind, _, _ = _classify_turn_error(Exception("Connection timed out reaching host"))
    assert kind == "network"


def test_classify_generic_model_error():
    kind, msg, _ = _classify_turn_error(Exception("something odd happened"))
    assert kind == "model" and "failed" in msg.lower()


# ---- crash-durable persistence: sanitize the thread before it reaches the model ----

def test_keeps_answered_toolcall_pair():
    ai = AIMessage(content="", tool_calls=[_tc("call_1")])
    tm = ToolMessage(content="ok", tool_call_id="call_1")
    assert _sanitize_thread([ai, tm]) == [ai, tm]


def test_plain_answer_kept():
    ai = AIMessage(content="final answer")
    assert _sanitize_thread([ai]) == [ai]


def test_dangling_empty_aimessage_dropped():
    pending = AIMessage(content="", tool_calls=[_tc("call_1")])   # result never arrived
    assert _sanitize_thread([pending]) == []


def test_dangling_aimessage_keeps_text_drops_toolcalls():
    pending = AIMessage(content="partial answer", tool_calls=[_tc("call_1")])
    out = _sanitize_thread([pending])
    assert len(out) == 1 and out[0].content == "partial answer" and not out[0].tool_calls


def test_orphan_toolmessage_dropped():
    orphan = ToolMessage(content="result", tool_call_id="ghost")
    assert _sanitize_thread([orphan]) == []


def test_mid_thread_dangling_cleaned_but_rest_kept():
    from langchain_core.messages import HumanMessage
    dangling = AIMessage(content="", tool_calls=[_tc("call_1")])  # crashed turn's tail
    follow = HumanMessage(content="next question")
    out = _sanitize_thread([dangling, follow])
    assert out == [follow]   # dangling (empty) dropped, the new human turn survives
