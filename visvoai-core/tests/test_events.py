import pytest

from langchain_core.messages import AIMessage, ToolMessage

from visvoai.core.events import (
    TextChunk,
    ToolEnd,
    ToolStart,
    TurnDone,
    agent_events,
)


class Chunk:
    def __init__(self, content):
        self.content = content


class FakeGraph:
    def __init__(self, events):
        self.events = events

    async def astream_events(self, state, config=None, version="v2"):
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_streaming_text_is_normalized():
    graph = FakeGraph(
        [
            {
                "event": "on_chat_model_start",
                "name": "model",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "parent_ids": ["root"],
                "data": {"chunk": Chunk("Hello ")},
            },
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "parent_ids": ["root"],
                "data": {"chunk": Chunk("world")},
            },
            {
                "event": "on_chat_model_end",
                "name": "model",
                "parent_ids": ["root"],
                "data": {
                    "output": AIMessage(content="Hello world"),
                },
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [
        event
        async for event in agent_events(
            graph,
            "hello",
            thread_id="t1",
        )
    ]

    assert events == [
        TextChunk("Hello "),
        TextChunk("world"),
        TurnDone(),
    ]


@pytest.mark.asyncio
async def test_non_streaming_model_emits_one_text_chunk():
    graph = FakeGraph(
        [
            {
                "event": "on_chat_model_start",
                "name": "model",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chat_model_end",
                "name": "model",
                "parent_ids": ["root"],
                "data": {
                    "output": AIMessage(content="Hello world"),
                },
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [event async for event in agent_events(graph, "hello")]

    assert events == [
        TextChunk("Hello world"),
        TurnDone(),
    ]


@pytest.mark.asyncio
async def test_tool_start_and_end_are_normalized():
    graph = FakeGraph(
        [
            {
                "event": "on_tool_start",
                "name": "service_status",
                "parent_ids": ["root"],
                "data": {"input": {"name": "database"}},
            },
            {
                "event": "on_tool_end",
                "name": "service_status",
                "parent_ids": ["root"],
                "data": {
                    "output": ToolMessage(
                        content="database is healthy",
                        tool_call_id="tc1",
                    )
                },
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [event async for event in agent_events(graph, "check database")]

    assert events == [
        ToolStart("service_status", {"name": "database"}),
        ToolEnd("service_status", "database is healthy"),
        TurnDone(),
    ]


@pytest.mark.asyncio
async def test_tool_call_model_output_does_not_emit_text():
    graph = FakeGraph(
        [
            {
                "event": "on_chat_model_start",
                "name": "model",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chat_model_end",
                "name": "model",
                "parent_ids": ["root"],
                "data": {
                    "output": AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "service_status",
                                "args": {"name": "database"},
                                "id": "tc1",
                                "type": "tool_call",
                            }
                        ],
                    )
                },
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [event async for event in agent_events(graph, "check database")]

    assert events == [TurnDone()]

@pytest.mark.asyncio
async def test_streaming_state_resets_for_each_model_invocation():
    graph = FakeGraph(
        [
            {
                "event": "on_chat_model_start",
                "name": "model",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "parent_ids": ["root"],
                "data": {"chunk": Chunk("Need a tool")},
            },
            {
                "event": "on_chat_model_end",
                "name": "model",
                "parent_ids": ["root"],
                "data": {
                    "output": AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "service_status",
                                "args": {"name": "database"},
                                "id": "tc1",
                                "type": "tool_call",
                            }
                        ],
                    )
                },
            },
            {
                "event": "on_tool_start",
                "name": "service_status",
                "parent_ids": ["root"],
                "data": {"input": {"name": "database"}},
            },
            {
                "event": "on_tool_end",
                "name": "service_status",
                "parent_ids": ["root"],
                "data": {
                    "output": ToolMessage(
                        content="database is healthy",
                        tool_call_id="tc1",
                    )
                },
            },
            {
                "event": "on_chat_model_start",
                "name": "model",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chat_model_end",
                "name": "model",
                "parent_ids": ["root"],
                "data": {
                    "output": AIMessage(
                        content="The database is healthy."
                    )
                },
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [event async for event in agent_events(graph, "check database")]

    assert events == [
        TextChunk("Need a tool"),
        ToolStart("service_status", {"name": "database"}),
        ToolEnd("service_status", "database is healthy"),
        TextChunk("The database is healthy."),
        TurnDone(),
    ]


@pytest.mark.asyncio
async def test_inner_chain_end_does_not_emit_turn_done():
    graph = FakeGraph(
        [
            {
                "event": "on_chain_end",
                "name": "should_continue",
                "parent_ids": ["root"],
                "data": {},
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "parent_ids": [],
                "data": {},
            },
        ]
    )

    events = [event async for event in agent_events(graph, "hello")]

    assert events == [TurnDone()]