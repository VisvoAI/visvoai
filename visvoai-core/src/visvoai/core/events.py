"""Normalize LangGraph streaming events into VisvoAI agent events."""

from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class TextChunk:
    text: str


@dataclass(frozen=True)
class ToolStart:
    name: str
    args: Any


@dataclass(frozen=True)
class ToolEnd:
    name: str
    result: Any


@dataclass(frozen=True)
class TurnDone:
    pass


def _extract_text_and_tools(output: Any) -> tuple[Any, list[Any]]:
    """Extract text content and tool calls from a chat-model output."""
    if not output:
        return "", []

    if hasattr(output, "generations") and output.generations:
        message = output.generations[0].message
        return (
            getattr(message, "content", ""),
            getattr(message, "tool_calls", []),
        )

    return (
        getattr(output, "content", ""),
        getattr(output, "tool_calls", []),
    )


async def agent_events(
    graph: Any,
    text: str,
    *,
    thread_id: str | None = None,
) -> AsyncIterator[TextChunk | ToolStart | ToolEnd | TurnDone]:
    """Yield normalized events for a single agent turn.

    Converts LangGraph's raw ``astream_events`` output into a small,
    transport-agnostic event vocabulary.
    """
    config = (
        {"configurable": {"thread_id": thread_id}}
        if thread_id is not None
        else None
    )

    streamed_text = False

    async for event in graph.astream_events(
        {"messages": [("user", text)]},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_start":
            # A single agent turn can contain multiple model invocations,
            # e.g. model -> tool -> model. The fallback applies per
            # model invocation, not to the whole turn.
            streamed_text = False

        elif kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content

            if content:
                streamed_text = True
                yield TextChunk(content)

        elif kind == "on_chat_model_end":
            output = event["data"].get("output")
            content, tool_calls = _extract_text_and_tools(output)

            # Some models return their complete response through
            # on_chat_model_end instead of streaming chunks.
            # Do not emit it twice when streaming already happened.
            if not streamed_text and content and not tool_calls:
                yield TextChunk(content)

        elif kind == "on_tool_start":
            yield ToolStart(
                event["name"],
                event["data"].get("input"),
            )

        elif kind == "on_tool_end":
            output = event["data"].get("output")

            yield ToolEnd(
                event["name"],
                getattr(output, "content", output),
            )

        elif (
            kind == "on_chain_end"
            and not event.get("parent_ids")
        ):
            # The root LangGraph runnable has no parent IDs.
            # Ignore inner chain completions; emit one event when
            # the outer graph finishes.
            yield TurnDone()