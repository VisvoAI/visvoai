"""
Background process registry for the CLI.

Long-running commands (dev servers, watchers) don't fit a synchronous tool call —
they need a home that outlives the call. `ProcessRegistry` is that home: spawn
detached, read output incrementally, stop on demand, and kill everything left at
app exit so a closed CLI never leaves a server squatting on a port.

Design points:
- One registry per app (not per turn): a server started in turn 1 is checked in
  turn 5. The TUI owns one instance; headless runs create one per invocation.
- New session per spawn (`start_new_session=True`) → the process GROUP is the
  kill target. `yarn dev` spawns children; killing just the parent leaks the
  actual server.
- Output goes to a bounded deque of lines (ring buffer) fed by a reader thread —
  no pipe for the child to block on, no unbounded memory from chatty servers.
- Registry survives turn cancellation untouched. It does NOT survive app restart:
  `get()` on an unknown id returns None and tools report that as data.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

MAX_BUFFER_LINES = 2000        # ring buffer per process
STOP_GRACE_S = 3.0             # SIGTERM → wait → SIGKILL


@dataclass
class ProcInfo:
    """Snapshot returned to callers — never the live handle."""
    id: str
    command: str
    pid: int
    status: str                 # "running" | "exited" | "stopped"
    returncode: Optional[int]
    started_at: float
    stopped_by: Optional[str]   # "user" | "agent" | None
    buffer_lines: int


class _Proc:
    def __init__(self, id: str, command: str, popen: subprocess.Popen) -> None:
        self.id = id
        self.command = command
        self.popen = popen
        self.started_at = time.time()
        self.stopped_by: Optional[str] = None
        self.lines: deque[str] = deque(maxlen=MAX_BUFFER_LINES)
        self.cursors: dict[str, int] = {}   # reader name -> lines consumed (monotonic)
        self.total_lines = 0
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        # Reader thread drains the pipe for the process's lifetime, so the child
        # can never block on a full pipe and the buffer is always current.
        stream = self.popen.stdout
        if stream is None:
            return
        for raw in stream:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
            with self._lock:
                # deque drops from the left when full; cursor math stays correct
                # because it tracks total_lines ever seen, not buffer indexes.
                self.lines.append(line.rstrip("\n"))
                self.total_lines += 1
        try:
            stream.close()
        except OSError:
            pass

    def status(self) -> str:
        if self.popen.poll() is None:
            return "running"
        return "stopped" if self.stopped_by else "exited"

    def read_new(self, reader: str = "agent") -> str:
        """Lines this reader hasn't seen yet (per-reader cursor, monotonic)."""
        with self._lock:
            seen = self.cursors.get(reader, 0)
            dropped = self.total_lines - len(self.lines)
            start = max(seen - dropped, 0)
            chunk = list(self.lines)[start:]
            self.cursors[reader] = self.total_lines
        prefix = ""
        if seen < dropped and seen != 0:
            prefix = f"…[{dropped - seen} earlier lines dropped from buffer]\n"
        elif seen == 0 and dropped > 0:
            prefix = f"…[{dropped} earlier lines dropped from buffer]\n"
        return prefix + "\n".join(chunk)

    def tail(self, n: int = 1) -> str:
        with self._lock:
            return "\n".join(list(self.lines)[-n:])

    def stop(self, by: str) -> None:
        if self.popen.poll() is not None:
            return
        self.stopped_by = by
        try:
            pgid = os.getpgid(self.popen.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
            deadline = time.time() + STOP_GRACE_S
            while time.time() < deadline:
                if self.popen.poll() is not None:
                    return
                time.sleep(0.05)
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass    # already gone between poll and kill

    def info(self) -> ProcInfo:
        return ProcInfo(
            id=self.id,
            command=self.command,
            pid=self.popen.pid,
            status=self.status(),
            returncode=self.popen.poll(),
            started_at=self.started_at,
            stopped_by=self.stopped_by,
            buffer_lines=len(self.lines),
        )


class ProcessRegistry:
    def __init__(self) -> None:
        self._procs: dict[str, _Proc] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def spawn(self, command: str, cwd: Optional[str] = None) -> ProcInfo:
        """Start a detached background process. Raises OSError on spawn failure."""
        popen = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,        # one interleaved stream, like a terminal
            stdin=subprocess.DEVNULL,
            start_new_session=True,          # own process group → group kill works
        )
        with self._lock:
            self._counter += 1
            pid_id = f"p{self._counter}"
            proc = _Proc(pid_id, command, popen)
            self._procs[pid_id] = proc
        return proc.info()

    def get(self, id: str) -> Optional[_Proc]:
        return self._procs.get(id)

    def list(self) -> list[ProcInfo]:
        return [p.info() for p in self._procs.values()]

    def running_count(self) -> int:
        return sum(1 for p in self._procs.values() if p.status() == "running")

    def dismiss(self, id: str) -> bool:
        """Drop a finished process from the registry (running ones must be
        stopped first — refuse silently dropping a live process)."""
        p = self._procs.get(id)
        if p is None or p.status() == "running":
            return False
        del self._procs[id]
        return True

    def stop_all(self, by: str = "shutdown") -> None:
        """Kill every running process group. Called on app exit — a closed CLI
        must never leave a dev server squatting on a port."""
        for p in list(self._procs.values()):
            p.stop(by)


def describe_cmd(command: str, width: int = 60) -> str:
    """One-line display form of a command (whitespace collapsed, ellipsized)."""
    flat = " ".join(command.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"
