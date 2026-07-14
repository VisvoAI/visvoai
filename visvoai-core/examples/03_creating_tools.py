"""Every way to create a tool — and when to use which.

    pip install visvoai-core
    python 03_creating_tools.py            # runs with NO api key

The graph binds any LangChain `BaseTool`, so there are four honest ways in,
from lightest to heaviest. Rule of thumb: start at 1; move down only when you
need what the next level adds.

  1. @tool                — one function, schema from type hints. 95% of tools.
  2. @tool + docstring    — same, but Google-style Args: sections become
     args                   per-argument descriptions the model actually reads.
  3. async def + @tool    — for I/O-bound work; the loop awaits it natively.
  4. BaseAgentTool        — the LIFECYCLE class: declared config, auto-
                            registration, persistence hooks (see
                            06_sqlite_audit_trail.py). For products that must
                            record/govern every call — this is the same seam a
                            hosted multi-tenant platform runs on.
"""
import asyncio

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# ── 1 · the default: one typed function ──────────────────────────────────────
@tool
def word_count(text: str) -> str:
    """Count the words in a text."""
    return str(len(text.split()))


# ── 2 · richer schema: per-arg descriptions + constrained types ──────────────
class SearchArgs(BaseModel):
    query: str = Field(description="What to look for")
    limit: int = Field(default=5, ge=1, le=50, description="Max results")


@tool(args_schema=SearchArgs)
def search_notes(query: str, limit: int = 5) -> str:
    """Search my notes and return the top matches."""
    return f"(pretend results for {query!r}, top {limit})"


# ── 3 · async: I/O-bound tools await on the loop, no threads ─────────────────
@tool
async def fetch_status(service: str) -> str:
    """Check a service's health endpoint."""
    await asyncio.sleep(0.05)               # stands in for an HTTP call
    return f"{service}: ok"


# ── 4 · the lifecycle class: config + registration + persistence hooks ───────
from visvoai.core.results import ToolResult
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
    # All four are real and invokable right now:
    print("1:", word_count.invoke({"text": "how many words is this"}))
    print("2:", search_notes.invoke({"query": "quarterly numbers", "limit": 3}))
    print("3:", asyncio.run(fetch_status.ainvoke({"service": "api"})))
    print("4:", SummarizeTool().execute(tool_call_id="demo",
                                        text="Tools four ways.\nMore lines…")["output"])

    # Styles 1–3 go straight into the graph (see 01_minimal_agent.py):
    #   AgentRuntime().build_graph(model=…, core_tools=[word_count, …], …)
    # Style 4 adds the lifecycle: inject a ToolPersistence and every call is
    # recorded — run 06_sqlite_audit_trail.py to see that end to end.
