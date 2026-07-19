"""A real ToolPersistence: every tool call audited into SQLite.

    pip install visvoai-core
    python 06_sqlite_audit_trail.py        # runs with NO api key

04_extend_the_runtime.py showed the persistence hooks firing; this shows why
they're shaped the way they are — implement four methods and every tool call
in your product lands in YOUR datastore with ids, inputs, status, duration.
No middleware, no wrapping at call sites: inject once on the tool instance,
the base class does the rest (including firing on_error and re-raising when
a tool blows up).

The hosted platform behind these packages does exactly this into Postgres;
the CLI ships JSONL traces the same way. Here: SQLite, ~30 lines.
"""
import sqlite3
from pydantic import BaseModel

from visvoai.core.persistence import ToolPersistence
from visvoai.core.tools import BaseAgentTool, tool_config


# ── the sink: four hooks, one table ──────────────────────────────────────────
class SqliteAudit(ToolPersistence):
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS tool_calls ("
            " id TEXT PRIMARY KEY, tool TEXT, input TEXT,"
            " status TEXT, duration_ms INT)")

    def on_start(self, *, tool_id, message_id, tool_name, tool_input,
                 agent_step, execution_phase=None, **kw):
        self.db.execute("INSERT INTO tool_calls VALUES (?,?,?,?,?)",
                        (tool_id, tool_name, repr(tool_input), "RUNNING", None))
        return tool_id          # you may mint/canonicalize ids here

    def on_complete(self, *, tool_id, status, output, duration_ms, **kw):
        self.db.execute("UPDATE tool_calls SET status=?, duration_ms=? WHERE id=?",
                        (status, duration_ms, tool_id))

    def on_error(self, *, tool_id, error, duration_ms, **kw):
        self.db.execute("UPDATE tool_calls SET status=?, duration_ms=? WHERE id=?",
                        (f"ERROR: {error}"[:80], duration_ms, tool_id))


# ── two tools: one succeeds, one raises — both are audited ───────────────────
class _Args(BaseModel):
    text: str


@tool_config(is_core=True)
class Upper(BaseAgentTool):
    name = "upper"
    description = "Uppercase text."
    args_schema = _Args

    def _execute(self, tool_call_id: str, **kwargs):
        return {"output": kwargs["text"].upper()}


@tool_config(is_core=True)
class Flaky(BaseAgentTool):
    name = "flaky"
    description = "Always fails."
    args_schema = _Args

    def _execute(self, tool_call_id: str, **kwargs):
        raise RuntimeError("upstream 503")


if __name__ == "__main__":
    audit = SqliteAudit()
    ok, bad = Upper(), Flaky()
    ok._persistence = audit
    bad._persistence = audit

    ok.execute(tool_call_id="call-1", text="audited")
    try:
        bad.execute(tool_call_id="call-2", text="boom")
    except RuntimeError:
        pass                    # the error is re-raised — AND recorded

    print(f"{'id':<8} {'tool':<7} {'status':<22} ms")
    for row in audit.db.execute(
            "SELECT id, tool, status, duration_ms FROM tool_calls"):
        print(f"{row[0]:<8} {row[1]:<7} {row[2]:<22} {row[3]}")
