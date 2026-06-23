# visvoai-core

An extensible agent runtime for Python, built on LangGraph. `visvoai-core` gives
you the agent↔tools loop, a tool base class with auto-registration, semantic
tool retrieval, and clean extension seams — with no datastore, web, or auth
dependencies. You subclass and inject what you need.

## Install

```bash
pip install visvoai-core
```

This pulls `visvoai-ai` (the LLM provider layer), `langgraph`, and
`langchain-core`. Install a provider extra to actually talk to a model, e.g.
`pip install "visvoai-ai[gemini]"`.

## Usage

```python
from visvoai.core.runtime import AgentRuntime
from visvoai.ai.providers.gemini import GeminiProvider

model = GeminiProvider().build_chat_model(model_id="gemini-2.5-flash")

runtime = AgentRuntime()
graph = runtime.build_graph(
    model=model,
    core_tools=[],          # your BaseTool / BaseAgentTool instances
    all_tools_map={},
    system_prompt="You are a helpful assistant.",
)

async for event in graph.astream_events({"messages": [("user", "Hi")]}, version="v2"):
    ...
```

## Writing a tool

```python
from visvoai.core.tools import BaseAgentTool, tool_config
from visvoai.core.results import ToolResult

@tool_config(is_core=True, routing_hint="Use to echo text back.")
class EchoTool(BaseAgentTool):
    name = "echo"
    description = "Echo the input back."
    args_schema = EchoArgs          # a pydantic BaseModel
    _owned_resource_checks = []

    def _execute(self, tool_call_id: str, **kwargs):
        return ToolResult.success(self.name, kwargs.get("text", ""))
```

Tools auto-register at definition time. `execute()` ships a default lifecycle
(start → run → complete/error); to record those events somewhere, inject a
`ToolPersistence` subclass on the tool instance — the default is a no-op, so
tools run standalone with no datastore.

## Extending

- **`AgentRuntime`** — subclass and override `_extend_graph()`, `_tools_routing()`,
  `_get_checkpointer()`, `_get_interrupt_nodes()` to add nodes (approval gates,
  background tasks), a checkpointer, or interrupt points.
- **`RuntimeContext`** — subclass to carry surface-specific state to your tools.
- **`AgentState`** — extend via TypedDict inheritance to add your own state fields.
- **`ToolResult` / `ToolStatus`** — subclass to widen the result envelope.

No forks, no patches — extension is subclassing plus injection.

## License

MIT
