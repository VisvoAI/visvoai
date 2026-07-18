"""The four ways to write a tool. All of them go into the same list.

    pip install visvoai-core
    python 03_creating_tools.py        # runs with NO api key

  1. A plain function        — most tools. No imports. Type hints become the
                               schema, the docstring becomes the description.
  2. A function with Args:   — same, plus one help line per argument.
                               The model reads it and picks arguments better.
  3. An async function       — for network/disk work; the loop awaits it.
  4. A lifecycle class       — for "serious" tools: declared schema, and
                               hooks that record every run in your database.

You can also pass any existing LangChain tool — it works unchanged.
`build_graph(core_tools=[...])` takes all of these, mixed in one list.
"""
import asyncio

from pydantic import BaseModel


# ── 1 · a plain function — this is a complete tool ───────────────────────────
def word_count(text: str) -> str:
    """Count the words in a piece of text."""
    return f"{len(text.split())} words"


# ── 2 · add an Args: section — one help line per argument ────────────────────
def search_notes(query: str, limit: int = 5) -> str:
    """Search my notes and return the closest matches.

    Args:
        query: What to look for, in plain words.
        limit: How many results to return at most.
    """
    return f"top {limit} notes matching {query!r}"


# ── 3 · async — the loop awaits it, no threads needed ────────────────────────
async def fetch_status(service: str) -> str:
    """Check if a service is up and return its status."""
    await asyncio.sleep(0)  # imagine a real network call here
    return f"{service}: ok"


# ── 4 · the lifecycle class — schema + hooks that record every run ───────────
from visvoai.core.tools import BaseAgentTool, tool_config


class SummarizeArgs(BaseModel):
    text: str


@tool_config(is_core=True, routing_hint="Use to summarize long text.")
class SummarizeTool(BaseAgentTool):
    name = "summarize"
    description = "Summarize text to one line."
    args_schema = SummarizeArgs

    def _execute(self, tool_call_id: str, **kwargs):
        first = kwargs["text"].strip().splitlines()[0][:80]
        return {"output": f"Summary: {first}…"}


if __name__ == "__main__":
    # as_tool() is what build_graph runs on your list — used here to show
    # each style is already a working tool:
    from visvoai.core import as_tool

    print("1:", as_tool(word_count).invoke({"text": "how many words is this"}))
    print("2:", as_tool(search_notes).invoke({"query": "quarterly numbers",
                                              "limit": 3}))
    print("3:", asyncio.run(as_tool(fetch_status).ainvoke({"service": "api"})))
    print("4:", SummarizeTool().execute(tool_call_id="demo",
                                        text="Tools four ways.\nMore lines…")["output"])

    # Proof the model sees your Args: help text (way 2):
    schema = as_tool(search_notes).args_schema.model_json_schema()
    print("   the model sees:", schema["properties"]["query"]["description"])

    # All four go straight into the graph (see 01_minimal_agent.py):
    #   AgentRuntime().build_graph(model=..., core_tools=[word_count,
    #       search_notes, fetch_status, SummarizeTool], ...)
    # The class (way 4) adds the lifecycle: inject a ToolPersistence and every
    # call is recorded — run 06_sqlite_audit_trail.py to see it end to end.
