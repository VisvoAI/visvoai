"""Tool intake normalization: every authoring shape reaches the loop."""
from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool, tool as lc_tool

from visvoai.core import as_tool, as_tools_map
from visvoai.core.tools import BaseAgentTool
from visvoai.core.results import ToolResult, ToolStatus
from pydantic import BaseModel


def test_plain_function_becomes_tool():
    def word_count(text: str) -> int:
        """Count words in text."""
        return len(text.split())

    t = as_tool(word_count)
    assert isinstance(t, BaseTool)
    assert t.name == "word_count"
    assert t.description == "Count words in text."
    assert t.invoke({"text": "a b c"}) == 3


@pytest.mark.asyncio
async def test_async_function_becomes_tool():
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        return f"ok:{url}"

    t = as_tool(fetch)
    assert await t.ainvoke({"url": "x"}) == "ok:x"


def test_function_without_docstring_rejected():
    def nameless(x: int) -> int:
        return x

    with pytest.raises(TypeError, match="docstring"):
        as_tool(nameless)


def test_lambda_rejected():
    with pytest.raises(TypeError):
        as_tool(lambda x: x)


def test_langchain_tool_passes_through():
    @lc_tool
    def echo(text: str) -> str:
        """Echo."""
        return text

    assert as_tool(echo) is echo


def test_agent_tool_class_and_instance():
    calls = []

    class Args(BaseModel):
        text: str

    class ShoutTool(BaseAgentTool):
        name = "shout"
        description = "Uppercase the text."
        args_schema = Args

        def _execute(self, tool_call_id: str, **kwargs):
            calls.append(tool_call_id)
            return ToolResult.success(self.name, kwargs["text"].upper())

    t = as_tool(ShoutTool)                      # class → instantiated
    assert t.name == "shout"
    result = t.invoke({"text": "hi"})
    assert result.data["output"] == "HI"
    assert calls, "lifecycle .execute() ran (tool_call_id assigned)"

    t2 = as_tool(ShoutTool())                   # instance → adapted
    assert t2.name == "shout"


def test_as_tools_map_mixes_shapes():
    def one(x: int) -> int:
        """One."""
        return x

    m = as_tools_map([one])
    assert set(m) == {"one"}
    assert isinstance(m["one"], BaseTool)


def test_not_a_tool_rejected():
    with pytest.raises(TypeError, match="Not a tool"):
        as_tool(42)


def test_args_section_becomes_per_arg_descriptions():
    def fetch(url: str, timeout: int = 10) -> str:
        """Check whether a URL is up.

        Args:
            url: The full URL to probe, including scheme.
            timeout: Seconds to wait before giving up.
        """
        return url

    t = as_tool(fetch)
    props = t.args_schema.model_json_schema()["properties"]
    assert props["url"]["description"] == "The full URL to probe, including scheme."
    assert props["timeout"]["description"] == "Seconds to wait before giving up."
    assert "Args:" not in t.description          # section consumed, not repeated


def test_plain_docstring_still_fine():
    def simple(x: int) -> int:
        """Double a number."""
        return x * 2

    t = as_tool(simple)
    assert t.invoke({"x": 2}) == 4


@pytest.mark.asyncio
async def test_ask_text_boundary():
    """ask(): text in, final answer out — no LangChain shapes in user code."""
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage

    from visvoai.core import ask
    from visvoai.core.runtime import AgentRuntime

    class M(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, m, *a, **kw):
            return AIMessage(content="the answer")

    def noop(x: str) -> str:
        """No-op."""
        return x

    graph = AgentRuntime().build_graph(model=M(responses=[]),
                                       core_tools=[noop],
                                       system_prompt="test")
    assert await ask(graph, "question?") == "the answer"


@pytest.mark.asyncio
async def test_ask_threads_memory():
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import MemorySaver

    from visvoai.core import ask
    from visvoai.core.runtime import AgentRuntime

    class M(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, m, *a, **kw):
            return AIMessage(content=f"seen {len(m)} messages")

    def noop(x: str) -> str:
        """No-op."""
        return x

    graph = AgentRuntime().build_graph(model=M(responses=[]),
                                       core_tools=[noop], system_prompt="t",
                                       checkpointer=MemorySaver())
    a1 = await ask(graph, "one", thread_id="t1")
    a2 = await ask(graph, "two", thread_id="t1")     # same thread: history grows
    b1 = await ask(graph, "one", thread_id="t2")     # fresh thread: resets
    assert a2 != a1 and b1 == a1
