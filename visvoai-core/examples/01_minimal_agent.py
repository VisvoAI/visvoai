"""A working agent in ~20 lines: model + tools + the visvoai-core loop.

    pip install visvoai-core "visvoai-ai[gemini]"
    export GEMINI_API_KEY=...
    python 01_minimal_agent.py

What core adds over wiring LangGraph yourself: a soft step cap that forces one
clean final answer (never a GraphRecursionError in your user's face), and
duplicate tool-call blocking. Tools are plain Python functions — the type
hints become the schema, the docstring becomes the description. No imports.
"""
import asyncio
from pathlib import Path

from visvoai.ai import build_chat_model
from visvoai.core.runtime import AgentRuntime


def list_dir(path: str = ".") -> str:
    """List the files in a directory."""
    return "\n".join(sorted(p.name for p in Path(path).iterdir()))


def read_file(path: str) -> str:
    """Read a text file and return its contents (first 200 lines)."""
    return "\n".join(Path(path).read_text().splitlines()[:200])


async def main() -> None:
    tools = [list_dir, read_file]
    graph = AgentRuntime().build_graph(
        model=build_chat_model("gemini:gemini-2.5-flash"),
        core_tools=tools,
        all_tools_map={t.name: t for t in tools},
        system_prompt="You are a concise code assistant. Use your tools.",
    )
    result = await graph.ainvoke(
        {"messages": [("user", "What does this directory contain?")]})
    print(result["messages"][-1].content)


asyncio.run(main())
