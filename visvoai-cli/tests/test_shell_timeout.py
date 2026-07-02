"""Regression: a backgrounded child holding the stdout pipe open used to crash
run_shell with TypeError (TimeoutExpired.stdout is bytes even with text=True).
The exact failure shape from the wild: `server & sleep; curl` hitting timeout."""
from __future__ import annotations

import asyncio

import pytest

from visvoai.cli.tools._common import as_text
from visvoai.cli.tools.shell import run_shell


def test_as_text_coerces():
    assert as_text(b"hi\xff") == "hi�"
    assert as_text("hi") == "hi"
    assert as_text(None) == ""


def test_run_shell_timeout_with_backgrounded_child_returns_data():
    # The child keeps the pipe open past the timeout; partial output was written.
    out = run_shell.func("sleep 30 & echo partial-output; sleep 0.2",
                         timeout_seconds=1)
    assert "timed out after 1s" in out
    assert "partial-output" in out          # partial output survives, decoded
    assert out.endswith("[exit: -1]")


@pytest.mark.asyncio
async def test_gated_run_shell_timeout_same_shape():
    from visvoai.cli.gated_tools import build_gated_tools

    async def approve(name, args):
        return True

    tools = {t.name: t for t in build_gated_tools(cwd=".", approve=approve)}
    out = await tools["run_shell"].coroutine(
        command="sleep 30 & echo partial-output; sleep 0.2", timeout_seconds=1)
    assert "timed out after 1s" in out
    assert "partial-output" in out
    assert out.endswith("[exit: -1]")
