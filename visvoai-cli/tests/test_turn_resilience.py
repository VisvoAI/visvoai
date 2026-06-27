"""Turn resilience: shell-timeout as a tool error, error classification, and the
replayable-suffix trim that lets an errored turn still persist."""
from __future__ import annotations

import subprocess

from langchain_core.messages import AIMessage, ToolMessage

from visvoai.cli.agent_turn import _classify_turn_error, _valid_thread_suffix
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


# ---- #5: replayable-suffix trim ----

def test_drops_trailing_unanswered_toolcall():
    done = AIMessage(content="hello")
    pending = AIMessage(content="", tool_calls=[_tc("call_1")])
    # call_1 never answered → the pending AIMessage must be dropped
    assert _valid_thread_suffix([done, pending]) == [done]


def test_keeps_answered_toolcall_pair():
    ai = AIMessage(content="", tool_calls=[_tc("call_1")])
    tm = ToolMessage(content="ok", tool_call_id="call_1")
    assert _valid_thread_suffix([ai, tm]) == [ai, tm]


def test_plain_answer_kept():
    ai = AIMessage(content="final answer")
    assert _valid_thread_suffix([ai]) == [ai]
