"""The extension seams: your persistence, your tool lifecycle, your runtime.

    pip install visvoai-core
    python 04_extend_the_runtime.py        # runs with NO api key — seams only

Three seams in one file — the same ones a hosted multi-tenant platform and the
visvoai-cli TUI build on (no forks, subclass + inject):

  1. BaseAgentTool    — declare config, write _execute(); the base class owns
                        the lifecycle (start → run → complete/error)
  2. ToolPersistence  — every lifecycle event recorded wherever YOU want
  3. AgentRuntime     — override hooks to reshape the agent graph itself
"""
from pydantic import BaseModel

from visvoai.core.persistence import ToolPersistence
from visvoai.core.runtime import AgentRuntime
from visvoai.core.tools import BaseAgentTool, tool_config


# ── 1 · a lifecycle tool: config declared, _execute() is all you write ───────
class ShoutArgs(BaseModel):
    text: str


@tool_config(is_core=True, routing_hint="Use to shout text back.")
class ShoutTool(BaseAgentTool):
    name = "shout"
    description = "Return the input text, uppercased."
    args_schema = ShoutArgs

    def _execute(self, tool_call_id: str, **kwargs):
        return {"output": kwargs["text"].upper()}


# ── 2 · persistence: replace the no-op default with YOUR sink ────────────────
class PrintPersistence(ToolPersistence):
    """A real implementation writes to Postgres/SQLite/OTLP — the hooks are
    the seam; this one just proves they fire, in order, with the data."""

    def on_start(self, *, tool_id, message_id, tool_name, tool_input,
                 agent_step, execution_phase=None, **kw):
        print(f"[persist] start    {tool_name}({tool_input})")
        return tool_id                       # you may rewrite/canonicalize ids

    def on_complete(self, *, tool_id, status, output, duration_ms, **kw):
        print(f"[persist] complete {status} in {duration_ms}ms → {output}")


# ── 3 · a custom runtime: reshape the graph via hooks ────────────────────────
class MyRuntime(AgentRuntime):
    """Real consumers use these hooks for approval gates, background-task
    nodes, checkpointers, interrupt points. Here: proof they're called."""

    def _extend_graph(self, workflow, tool_configs):
        print(f"[runtime] _extend_graph — add your nodes to {type(workflow).__name__}")

    def _get_interrupt_nodes(self):
        return None                          # e.g. ["approval_gate"] for human-in-the-loop approval


if __name__ == "__main__":
    # Seam 1+2 — the tool lifecycle, standalone (no model, no graph needed):
    tool = ShoutTool()
    tool._persistence = PrintPersistence()   # inject: YOUR datastore
    result = tool.execute(tool_call_id="demo-1", text="hello seams")
    print(f"tool returned: {result['output']}\n")

    # Seam 3 — the runtime builds a standard LangGraph app; plain LangChain
    # @tool functions go in core_tools (see 03_minimal_agent.py). A fake model
    # object is enough to show the hook firing at build time:
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    MyRuntime().build_graph(
        model=FakeListChatModel(responses=["ok"]),
        core_tools=[],
        all_tools_map={},
        system_prompt="demo",
    )
    print("graph built — hooks ran.")
