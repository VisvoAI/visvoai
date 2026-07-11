"""AgentRunRegistry — live + finished subagent dispatches.

Model: an agent run IS an agent conversation — same structure as a main turn,
no human in it. So a run's activity is STRUCTURED steps (tool, target, status,
duration, output), never flattened log strings: the panel and /runs render them
with the same ToolRow widgets the conversation uses.

Lifecycle (the run_agent tool owns it — it knows the real dispatch id, the
task, and holds the cancellable asyncio task):
  register() at dispatch → step_start()/step_end() fed by the turn worker from
  the tagged event stream → finish() by the tool (or stop() by the user from
  /runs, which cancels the task; the tool returns "stopped by user").

Durability: every mutation appends to the run's JSONL trace file immediately —
a hung or killed run leaves its partial transcript on disk, exactly like a
crashed main turn keeps its persisted messages. Everything runs on the UI
event loop; no locks.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

STEP_CAP = 500          # structured steps kept in memory per run
RUN_CAP = 50            # finished runs kept before the oldest are dropped


@dataclass
class Step:
    key: str                     # event run_id — pairs start with end
    tool: str
    target: str
    status: str = "running"      # running | complete | failed
    output: str = ""             # first meaningful output line
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None

    @property
    def duration_s(self) -> float:
        return (self.ended or time.monotonic()) - self.started


@dataclass
class AgentRun:
    dispatch_id: str
    agent: str
    task: str
    started_at: float = field(default_factory=time.time)
    status: str = "running"            # running | done | failed | stopped
    steps: list = field(default_factory=list)
    summary: str = ""                  # telemetry trailer once finished
    final: str = ""                    # the agent's final answer (on finish)
    ended_at: float | None = None
    trace_path: Path | None = None
    cancel = None                      # () -> None; set by run_agent
    user_stopped: bool = False

    @property
    def duration_s(self) -> float:
        return (self.ended_at or time.time()) - self.started_at

    def _append_trace(self, record: dict) -> None:
        if self.trace_path is None:
            return
        try:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:   # tracing is best-effort, never fatal
            logger.warning("agent trace append failed (ignored): %s", e)


class AgentRunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}   # dispatch_id → run (insertion-ordered)

    # ── lifecycle (driven by the run_agent tool) ─────────────────────────────
    def register(self, dispatch_id: str, agent: str, task: str,
                 trace_path: Path | None = None, cancel=None) -> AgentRun:
        run = AgentRun(dispatch_id=dispatch_id, agent=agent, task=task,
                       trace_path=trace_path)
        run.cancel = cancel
        self._runs[dispatch_id] = run
        run._append_trace({"kind": "meta", "agent": agent,
                           "dispatch_id": dispatch_id, "task": task[:2000]})
        finished = [k for k, r in self._runs.items() if r.status != "running"]
        for k in finished[: max(0, len(self._runs) - RUN_CAP)]:
            del self._runs[k]
        return run

    def finish(self, dispatch_id: str, ok: bool, summary: str = "",
               final: str = "") -> None:
        run = self._runs.get(dispatch_id)
        if run is None or run.status != "running":
            return
        run.status = "stopped" if run.user_stopped else ("done" if ok else "failed")
        run.summary = summary
        run.final = final
        run.ended_at = time.time()
        for s in run.steps:                      # a dying run has no ✓ pending
            if s.status == "running":
                s.status = "failed"
                s.ended = time.monotonic()
        run._append_trace({"kind": "summary", "status": run.status,
                           "summary": summary, "final": final[:4000],
                           "duration_s": round(run.duration_s, 1)})

    def stop(self, dispatch_id: str) -> bool:
        """User-initiated stop of ONE run (from /runs). Cancels the dispatch
        task; run_agent turns the cancellation into a 'stopped by user' result
        for the caller — the main turn survives."""
        run = self._runs.get(dispatch_id)
        if run is None or run.status != "running" or run.cancel is None:
            return False
        run.user_stopped = True
        try:
            run.cancel()
        except Exception:
            return False
        return True

    # ── steps (fed by the turn worker from the tagged event stream) ──────────
    def step_start(self, dispatch_id: str, key: str, tool: str, target: str) -> None:
        run = self._runs.get(dispatch_id)
        if run is None:
            return
        if len(run.steps) >= STEP_CAP:
            return
        run.steps.append(Step(key=key, tool=tool, target=target))

    def step_end(self, dispatch_id: str, key: str, output: str, ok: bool) -> None:
        run = self._runs.get(dispatch_id)
        if run is None:
            return
        for s in reversed(run.steps):
            if s.key == key and s.status == "running":
                s.status = "complete" if ok else "failed"
                s.output = output[:300]
                s.ended = time.monotonic()
                run._append_trace({"kind": "step", "tool": s.tool,
                                   "target": s.target[:500], "ok": ok,
                                   "output": s.output,
                                   "duration_s": round(s.duration_s, 1)})
                return

    # ── views ─────────────────────────────────────────────────────────────────
    def runs(self) -> list[AgentRun]:
        """Running first (newest first within each group)."""
        return sorted(self._runs.values(),
                      key=lambda r: (r.status != "running", -r.started_at))

    def running_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.status == "running")
