"""The capstone: visvoai-ai + visvoai-core composed into one small product.

    pip install visvoai-core "visvoai-ai[gemini]"
    python 07_everything_together.py       # runs with NO api key (scripted model)
    GEMINI_API_KEY=... python 07_everything_together.py   # same code, live model

A tiny "ops assistant" that composes what examples 01–06 showed one piece at
a time:

  · the model chosen by FACTS from the registry            (visvoai-ai)
  · tools in three shapes, mixed in one list               (plain fn / Args: fn / lifecycle class)
  · every lifecycle-tool call AUDITED into SQLite          (ToolPersistence)
  · ten tools indexed, only matching ones bound per turn   (ToolCatalog retrieval)
  · multi-turn memory — "restart *it*" resolves via state  (checkpointer)

This file is the shape of a real product; everything else is business logic.
"""
import asyncio
import os
import sqlite3
import tempfile

from pydantic import BaseModel

from visvoai.core.persistence import ToolPersistence
from visvoai.core.tools import BaseAgentTool, tool_config


# ── tools, three shapes ──────────────────────────────────────────────────────
def disk_usage(path: str = "/") -> str:
    """Report how much disk space a path uses."""
    return f"{path}: 42.0 GB used, 12.0 GB free"


def service_status(name: str, region: str = "eu-west") -> str:
    """Check whether a service is healthy.

    Args:
        name: The service to check, e.g. "api" or "worker".
        region: Deployment region to check in.
    """
    return f"{name} in {region}: healthy, 12ms p50"


class RestartArgs(BaseModel):
    name: str


@tool_config(is_core=True, routing_hint="Use to restart a service by name.")
class RestartService(BaseAgentTool):
    name = "restart_service"
    description = "Restart a service. The only tool here that changes anything."
    args_schema = RestartArgs

    def _execute(self, tool_call_id: str, **kwargs):
        return {"output": f"{kwargs['name']} restarted, healthy after 3.2s"}


# realistic clutter — retrieval must surface the right tools past these
def _mk(n: str):
    def f(query: str) -> str:
        return f"{n}: no data"
    f.__name__ = n
    f.__doc__ = f"Query the {n.replace('_', ' ')} system."
    return f

FLEET = [_mk(n) for n in (
    "billing_lookup", "dns_records", "cert_expiry", "queue_depth",
    "error_budget", "release_notes", "oncall_roster")]


# ── persistence: every restart lands in an audit table ───────────────────────
class SqliteAudit(ToolPersistence):
    def __init__(self, db: str) -> None:
        # check_same_thread: sync tools run on an executor thread
        self.conn = sqlite3.connect(db, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS audit "
                          "(tool TEXT, input TEXT, status TEXT, ms INTEGER)")

    def on_start(self, tool_id, message_id, tool_name, tool_input, **kw):
        self.conn.execute("INSERT INTO audit VALUES (?, ?, 'STARTED', 0)",
                          (tool_name, str(tool_input)))
        self.conn.commit()
        return tool_id

    def on_complete(self, tool_id, status, output, duration_ms, **kw):
        self.conn.execute("UPDATE audit SET status=?, ms=? WHERE rowid="
                          "(SELECT MAX(rowid) FROM audit)", (status, duration_ms))
        self.conn.commit()

    def on_error(self, tool_id, error, duration_ms, **kw):
        self.on_complete(tool_id, "ERROR", {}, duration_ms)


# ── model: picked by registry facts, or a scripted stand-in with no key ──────
def pick_model():
    if os.environ.get("GEMINI_API_KEY"):
        from visvoai.ai import Capability, build_chat_model, list_deployments
        cheap = min((d for d in list_deployments(Capability.CHAT)
                     if d.id.startswith("gemini:gemini-2.5-flash")
                     and "lite" not in d.id),
                    key=lambda d: d.input_cost_per_million)
        print(f"live model: {cheap.id}  "
              f"(${cheap.input_cost_per_million}/M in, "
              f"${cheap.output_cost_per_million}/M out)")
        return build_chat_model(cheap.id)

    print("no GEMINI_API_KEY — scripted model (same graph, same code)")
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage

    class ScriptedModel(FakeMessagesListChatModel):
        _queue = []                      # class-level: shared across bound clones

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages, *a, **kw):
            return type(self)._queue.pop(0)

    ScriptedModel._queue = [
        AIMessage(content="", tool_calls=[{"name": "service_status", "id": "1",
                                           "args": {"name": "api",
                                                    "region": "eu-west"}}]),
        AIMessage(content="api is healthy in eu-west (12ms p50)."),
        AIMessage(content="", tool_calls=[{"name": "restart_service", "id": "2",
                                           "args": {"name": "api"}}]),
        AIMessage(content="Restarted api — healthy again after 3.2s."),
    ]
    return ScriptedModel(responses=[])


# ── the product ──────────────────────────────────────────────────────────────
async def main() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from visvoai.core import as_tool, as_tools, ask
    from visvoai.core.retrieval import ToolCatalog
    from visvoai.core.runtime import AgentRuntime

    model = pick_model()

    audit_db = os.path.join(tempfile.mkdtemp(), "audit.db")
    restart = RestartService()
    restart._persistence = SqliteAudit(audit_db)

    core = as_tools([service_status, as_tool(restart)])   # always bound
    fleet = as_tools([disk_usage, *FLEET])                # bound on demand
    all_map = {t.name: t for t in (*core, *fleet)}

    catalog = ToolCatalog([(t.name, t.description) for t in fleet])

    def retrieve(query: str):
        names = catalog.search(query, k=3)
        print(f"   [retrieval] deferred tools bound this round: {names}")
        return names

    graph = AgentRuntime().build_graph(
        model=model,
        core_tools=core,
        all_tools_map=all_map,
        system_prompt="You are a calm ops assistant. Use tools; be brief.",
        per_round_retrieve=retrieve,
        checkpointer=MemorySaver(),
    )

    for question in ("is the api healthy in eu-west? and how is our error budget?",
                     "restart it anyway, please"):        # "it" needs memory
        print(f"\n➤ {question}")
        print("  ", await ask(graph, question, thread_id="shift-42"))

    rows = sqlite3.connect(audit_db).execute(
        "SELECT tool, status, ms FROM audit").fetchall()
    print("\naudit trail (SQLite):", rows)


if __name__ == "__main__":
    asyncio.run(main())
