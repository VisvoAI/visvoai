"""Stream the agent's work live — the pattern every real UI is built on.

    pip install visvoai-core "visvoai-ai[gemini]"
    export GEMINI_API_KEY=...
    python 04_streaming_events.py

The graph is a standard LangGraph app, so astream_events(v2) gives you every
step as it happens: model text chunks, tool starts, tool results. This ~30-line
consumer is, structurally, exactly what the visvoai-cli TUI does at scale.
"""
import asyncio
from pathlib import Path

from langchain_core.tools import tool
from visvoai.ai import build_chat_model
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
    async for ev in graph.astream_events(
            {"messages": [("user", "How long is 01_minimal_agent.py?")]},
            version="v2"):
        kind = ev["event"]
        if kind == "on_chat_model_stream":
            chunk = ev["data"]["chunk"]
            if isinstance(chunk.content, str) and chunk.content:
                print(chunk.content, end="", flush=True)
        elif kind == "on_tool_start":
            print(f"\n[tool: {ev['name']} {ev['data'].get('input', {})}]")
        elif kind == "on_tool_end":
            out = ev["data"]["output"]
            print(f"[  →  {getattr(out, 'content', out)}]")
    print()


asyncio.run(main())
