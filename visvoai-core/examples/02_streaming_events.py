"""Stream the agent's work live.

    pip install visvoai-core "visvoai-ai[gemini]"
    export GEMINI_API_KEY=...
    python 02_streaming_events.py

The graph is a standard LangGraph app. agent_events() normalizes its raw
astream_events(v2) output into a small, transport-agnostic event vocabulary:
text chunks, tool starts, tool ends, and turn completion.
"""
import asyncio
from pathlib import Path

from langchain_core.tools import tool
from visvoai.ai import build_chat_model
from visvoai.core.events import (
    TextChunk,
    ToolStart,
    ToolEnd,
    TurnDone,
    agent_events,
)
from visvoai.core.runtime import AgentRuntime


@tool
def count_lines(path: str) -> str:
    """Count the lines in a file."""
    return str(len(Path(path).read_text().splitlines()))


async def main() -> None:
    tools = [count_lines]
    graph = AgentRuntime().build_graph(
        model=build_chat_model("gemini:gemini-2.5-flash"),
        core_tools=tools,
        all_tools_map={t.name: t for t in tools},
        system_prompt="You are a code assistant.",
    )

    async for ev in agent_events(
        graph,
        "How long is 01_minimal_agent.py?",
    ):
        match ev:
            case TextChunk(text):
                print(text, end="", flush=True)

            case ToolStart(name, args):
                print(f"\n[tool: {name} {args}]")

            case ToolEnd(name, result):
                print(f"[  →  {result}]")

            case TurnDone():
                pass

    print()


asyncio.run(main())
