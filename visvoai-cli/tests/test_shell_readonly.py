"""shellsafe: read/write classification + OS sandbox enforcement + gate wiring.

Three layers under test:
1. classify_command — conservative text classifier (decides prompting only)
2. sandbox_argv / kernel enforcement — read-classified commands cannot write
3. gated run_shell — read commands skip approve(), writes still prompt,
   sandbox-denied "reads" fall back to the prompt path
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess

import pytest

from visvoai.cli.gated_tools import build_gated_tools
from visvoai.cli.tools.shellsafe import (
    classify_command, looks_sandbox_denied, sandbox_argv,
)

READ_COMMANDS = [
    "ls -la",
    "cat foo.py | grep x | wc -l",
    "git log --oneline -5",
    "git status && git diff",
    'rg -n "foo" src/',
    'find . -name "*.py"',
    "grep x f 2>/dev/null",
    "ls > /dev/null",
    "git branch",
    "git config user.name",
    "sed -n 1,5p f",
    "docker ps",
    "FOO=1 env",
    "timeout 5 grep x f",
    'awk "{print}" f',
    "/usr/bin/grep x f",
    "pytest --collect-only 2>&1 | head -3" .replace("pytest", "cat"),  # fd-dup is safe
]

WRITE_COMMANDS = [
    "rm -rf /tmp/x",
    "echo hi > f.txt",
    "echo hi >> f.txt",
    "git commit -m x",
    "git branch -D foo",
    "git config --add x y",
    'sed -i "" s/a/b/ f',
    'find . -name "*.pyc" -delete',
    "find . -exec rm {} ;",
    "echo $(rm -rf /)",
    "cat `ls`",
    'python -c "open(1)"',
    "npm install",
    "curl http://x",
    "tee f.txt",
    "docker rm x",
    "xargs rm",
    "",
    "pytest 2>&1 | tail -5",   # unknown verb → write even in a read-looking pipe
    "make build 2>/dev/null",
]


@pytest.mark.parametrize("cmd", READ_COMMANDS)
def test_classifies_read(cmd):
    assert classify_command(cmd) == "read"


@pytest.mark.parametrize("cmd", WRITE_COMMANDS)
def test_classifies_write(cmd):
    assert classify_command(cmd) == "write"


needs_sandbox = pytest.mark.skipif(
    not ((platform.system() == "Darwin" and shutil.which("sandbox-exec"))
         or (platform.system() == "Linux" and shutil.which("bwrap"))),
    reason="no OS sandbox available on this platform",
)


@needs_sandbox
def test_sandbox_allows_reads():
    r = subprocess.run(sandbox_argv("ls / | head -3"), capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip()


@needs_sandbox
@pytest.mark.parametrize("cmd,path", [
    ("touch {p}", "/tmp/shellsafe_touch"),
    ("python3 -c \"open('{p}','w')\"", "/tmp/shellsafe_py"),
    ('awk "BEGIN{{print > \\"{p}\\"}}"', "/tmp/shellsafe_awk"),
])
def test_sandbox_blocks_disguised_writes(cmd, path):
    """The kernel, not the classifier, is the boundary: even write vectors the
    classifier can't see (interpreters, awk redirection) must fail AND leave no file."""
    try:
        r = subprocess.run(sandbox_argv(cmd.format(p=path)),
                           capture_output=True, text=True)
        assert r.returncode != 0
        assert not os.path.exists(path)
    finally:
        if os.path.exists(path):
            os.unlink(path)


@needs_sandbox
def test_sandbox_denial_is_detected():
    r = subprocess.run(sandbox_argv("touch /tmp/shellsafe_det"),
                       capture_output=True, text=True)
    assert looks_sandbox_denied(r.stdout + r.stderr, r.returncode)
    assert not os.path.exists("/tmp/shellsafe_det")


def test_denial_detection_ignores_success():
    assert not looks_sandbox_denied("Operation not permitted", 0)


# ---------------------------------------------------------------------------
# Gate wiring: read → no prompt; write → prompt; denied write → no mutation.

def _shell_tool(cwd, approve):
    tools = build_gated_tools(str(cwd), approve)
    return next(t for t in tools if t.name == "run_shell")


@pytest.mark.asyncio
async def test_read_command_skips_approval(tmp_path):
    calls = []

    async def approve(name, args):
        calls.append(name)
        return True

    (tmp_path / "hello.txt").write_text("hi")
    out = await _shell_tool(tmp_path, approve).coroutine(
        command=f"ls {tmp_path}")
    assert "hello.txt" in out
    assert "[exit: 0]" in out
    assert calls == []          # never prompted


@pytest.mark.asyncio
async def test_write_command_prompts_and_runs(tmp_path):
    calls = []

    async def approve(name, args):
        calls.append(args["command"])
        return True

    target = tmp_path / "made.txt"
    out = await _shell_tool(tmp_path, approve).coroutine(
        command=f"touch {target}")
    assert calls and "touch" in calls[0]
    assert "[exit: 0]" in out
    assert target.exists()


@pytest.mark.asyncio
async def test_denied_write_does_not_run(tmp_path):
    async def approve(name, args):
        return False

    target = tmp_path / "never.txt"
    out = await _shell_tool(tmp_path, approve).coroutine(
        command=f"touch {target}")
    assert "declined" in out
    assert not target.exists()


@needs_sandbox
@pytest.mark.asyncio
async def test_misclassified_write_falls_back_to_prompt(tmp_path):
    """A write disguised as a read (here: awk redirection — verb is on the read
    list) is blocked by the sandbox, then rerouted through the approval prompt.
    Denying leaves no file; the silent-write path does not exist."""
    calls = []

    async def approve(name, args):
        calls.append(name)
        return False

    target = tmp_path / "smuggled.txt"
    cmd = f'awk "BEGIN{{print > \\"{target}\\"}}"'
    assert classify_command(cmd) == "read"      # the classifier IS fooled
    out = await _shell_tool(tmp_path, approve).coroutine(command=cmd)
    assert calls == ["run_shell"]               # ...but the user still got asked
    assert "declined" in out
    assert not target.exists()
