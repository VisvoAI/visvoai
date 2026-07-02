"""Background process tools: start_process / check_process / stop_process.

Built per-app via a factory (like make_write_file) so they share the app's
ProcessRegistry. The workflow the docstrings teach the model:

    start_process("yarn dev")            → {id: p1} immediately
    check_process("p1", wait_seconds=8)  → new output; repeat until "ready"
    …do the actual work (curl, tests, web_fetch)…
    stop_process("p1")                   → when finished with it

All failure modes return strings (never raise): unknown id, already-exited,
spawn failure. `approve` is optional — when given, start/stop are gated the
same way as run_shell (spawning is an external action; check is read-only).
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, List, Optional

from langchain_core.tools import BaseTool, tool

from visvoai.cli.processes import ProcessRegistry
from visvoai.cli.tools._common import cap_lines

CHECK_LINE_CAP = 300          # max lines one check_process returns
WAIT_MAX_S = 60

ApproveFn = Callable[[str, dict], Awaitable[bool]]

_DENIED = "User declined this action. No changes were made — adjust the plan or ask why."


def _unknown(process_id: str) -> str:
    return (f"ERROR: unknown process '{process_id}' — it may predate a CLI restart "
            f"(the registry does not survive restarts). Start a fresh one with "
            f"start_process.")


def build_background_tools(registry: ProcessRegistry, cwd: Optional[str] = None,
                           approve: Optional[ApproveFn] = None) -> List[BaseTool]:
    """The three background-process tools bound to `registry`."""

    @tool
    async def start_process(command: str) -> str:
        """Start a LONG-RUNNING command (dev server, watcher, tail) in the
        background and return immediately with a process id.

        Use this instead of run_shell for anything that doesn't exit on its own —
        run_shell would block until timeout. After starting, call
        check_process(id, wait_seconds=…) to read its output and wait for it to
        be ready (e.g. a "listening on port" line) BEFORE acting on it. Stop it
        with stop_process(id) when you no longer need it.

        Output (stdout+stderr interleaved) is captured to a bounded buffer you
        read via check_process. Working directory: the CLI's cwd."""
        if approve is not None and not await approve("start_process", {"command": command}):
            return _DENIED
        try:
            info = await asyncio.to_thread(registry.spawn, command, cwd)
        except OSError as e:
            return f"ERROR: could not start process: {e}"
        return (f"started {info.id} (pid {info.pid}): {command}\n"
                f"Call check_process(\"{info.id}\", wait_seconds=…) to see its output.")

    @tool
    async def check_process(process_id: str, wait_seconds: int = 0) -> str:
        """Read a background process's NEW output (since your last check) and its
        status.

        wait_seconds > 0 (max 60): keep collecting for that long before
        returning — use it to wait for a server to boot instead of calling in a
        tight loop. Returns immediately once the process exits. If the process
        printed nothing new, says so — that is normal for quiet servers."""
        proc = registry.get(process_id)
        if proc is None:
            return _unknown(process_id)

        wait = max(0, min(int(wait_seconds or 0), WAIT_MAX_S))
        if wait and proc.status() == "running":
            deadline = time.time() + wait
            while time.time() < deadline and proc.status() == "running":
                await asyncio.sleep(0.2)

        info = proc.info()
        out = proc.read_new(reader="agent")
        body = cap_lines(out.strip(), CHECK_LINE_CAP) if out.strip() else "(no new output)"
        if info.status == "running":
            status = "status: running"
        elif info.status == "stopped":
            by = info.stopped_by or "unknown"
            status = (f"status: stopped by the {by}"
                      + (f" (exit {info.returncode})" if info.returncode is not None else ""))
        else:
            status = f"status: exited (code {info.returncode})"
        return f"{body}\n[{info.id} — {status}]"

    @tool
    async def stop_process(process_id: str) -> str:
        """Stop a background process you started (SIGTERM to its whole process
        group, SIGKILL after a grace period). Do this when the server/watcher is
        no longer needed — don't leave processes running at the end of a task."""
        proc = registry.get(process_id)
        if proc is None:
            return _unknown(process_id)
        if proc.status() != "running":
            info = proc.info()
            return f"{process_id} already {info.status} (exit {info.returncode})."
        if approve is not None and not await approve(
                "stop_process", {"process_id": process_id, "command": proc.command}):
            return _DENIED
        await asyncio.to_thread(proc.stop, "agent")
        info = proc.info()
        return f"stopped {process_id} (exit {info.returncode})."

    # The model sees docstrings verbatim — dedent the factory-built tools'.
    import inspect
    for t in (start_process, check_process, stop_process):
        t.description = inspect.cleandoc(t.description)
    return [start_process, check_process, stop_process]
