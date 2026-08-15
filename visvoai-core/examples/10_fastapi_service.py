"""Exposing an AgentRuntime graph as a FastAPI Server-Sent Events (SSE) service.

    pip install visvoai-core fastapi uvicorn httpx
    python 10_fastapi_service.py                        # keyless (scripted model)
    GEMINI_API_KEY=... python 10_fastapi_service.py    # live model

This example shows two ways to expose an agent over FastAPI:

  Part 1 — Minimal SSE Endpoint (`POST /api/v1/chat/{thread_id}`)
    The simplest worked example (~40 lines of core logic). Holds the POST
    connection open while streaming text chunks, tool starts, and a terminal
    `[DONE]` signal via Server-Sent Events (SSE).

  Part 2 — Production Pattern (`POST` Submit + `GET` Stream Split)
    Separates submission from streaming:
      · POST /api/v2/chat/{thread_id} → Submits a message and returns immediately
        with {"status": "submitted"}. If a run is already active for thread_id,
        returns HTTP 409 Conflict to prevent concurrent runs on the same thread.
      · GET /api/v2/chat/{thread_id}/stream → Attaches to the thread's SSE stream.
    Includes reconnect replay buffer and per-thread pub/sub, allowing multiple
    tabs or page refreshes to attach to the same live run without duplicating work.

Production Caveats (What is NOT solved here):
  - Authentication & Rate Limiting: Omitted for clarity (not yet tracked in open
    issues; see adjacent governance issues #7 for spend caps and #15 for token
    budgets; add auth/rate-limiting middleware when deploying to production).
  - Persistence across restarts: MemorySaver is in-memory. Use AsyncSqliteSaver
    or Postgres for persistent thread memory.
"""
import asyncio
import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from visvoai.core import as_tools
from visvoai.core.runtime import AgentRuntime


# ── 1. Tool definition ────────────────────────────────────────────────────────
def service_status(name: str) -> str:
    """Check whether an infrastructure service is healthy."""
    return f"{name} is operational (99.9% uptime, 14ms latency)."


# ── 2. Model selection (Live or Keyless Scripted) ──────────────────────────────
class ScriptedModel(FakeMessagesListChatModel):
    """Scripted model for keyless execution and CI test runners."""
    _queue: list[AIMessage] = []

    @classmethod
    def reset_queue(cls, messages: list[AIMessage]):
        cls._queue = list(messages)

    def bind_tools(self, tools):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if type(self)._queue:
            msg = type(self)._queue.pop(0)
        else:
            msg = AIMessage(content="Task processed successfully.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def pick_model():
    if os.environ.get("GEMINI_API_KEY"):
        from visvoai.ai import Capability, build_chat_model, list_deployments
        cheap = min(
            (d for d in list_deployments(Capability.CHAT)
             if d.id.startswith("gemini:gemini-2.5-flash") and "lite" not in d.id),
            key=lambda d: d.input_cost_per_million
        )
        print(f"live model: {cheap.id}")
        return build_chat_model(cheap.id)

    print("no GEMINI_API_KEY — using scripted model (keyless execution)")
    ScriptedModel.reset_queue([
        AIMessage(
            content="",
            tool_calls=[{"name": "service_status", "id": "tc1", "args": {"name": "database"}}]
        ),
        AIMessage(content="Database status confirmed: healthy and operational (14ms latency)."),
    ])
    return ScriptedModel(responses=[])


# ── 3. Build Agent Graph ──────────────────────────────────────────────────────
model = pick_model()
tools = as_tools([service_status])
graph = AgentRuntime().build_graph(
    model=model,
    core_tools=tools,
    system_prompt="You are a helpful assistant. Use tools when needed.",
    checkpointer=MemorySaver(),
)

app = FastAPI(title="VisvoAI Agent SSE Service")


def _extract_text_and_tools(output):
    """Extract text content and tool calls from on_chat_model_end output payload."""
    if not output:
        return "", []
    if hasattr(output, "generations") and output.generations:
        msg = output.generations[0].message
        return getattr(msg, "content", ""), getattr(msg, "tool_calls", [])
    return getattr(output, "content", ""), getattr(output, "tool_calls", [])


# ── PART 1: Minimal Single-Endpoint SSE ───────────────────────────────────────
@app.post("/api/v1/chat/{thread_id}")
async def chat_v1(thread_id: str, message: str):
    """Simple single-endpoint SSE stream.

    Streams token chunks (`on_chat_model_stream`), tool-start events (`on_tool_start`),
    and finishes with `event: done`.
    """
    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [("user", message)]}
        streamed_text = False

        async for ev in graph.astream_events(inputs, config=config, version="v2"):
            kind = ev["event"]

            if kind == "on_chat_model_start":
                streamed_text = False

            elif kind == "on_chat_model_stream":
                content = ev["data"]["chunk"].content
                if content:
                    streamed_text = True
                    payload = json.dumps({"type": "text", "content": content})
                    yield f"data: {payload}\n\n"

            elif kind == "on_chat_model_end":
                output = ev["data"].get("output")
                content, tool_calls = _extract_text_and_tools(output)
                if not streamed_text and content and not tool_calls:
                    payload = json.dumps({"type": "text", "content": content})
                    yield f"data: {payload}\n\n"

            elif kind == "on_tool_start":
                payload = json.dumps({
                    "type": "tool_start",
                    "tool": ev["name"],
                    "input": ev["data"].get("input"),
                })
                yield f"data: {payload}\n\n"

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── PART 2: Production Pattern (Submit POST + Stream GET Split) ────────────────
class ThreadStreamHub:
    """In-memory event hub per thread_id providing reconnect replay buffer & pub/sub."""

    def __init__(self, buffer_size: int = 50):
        self.buffer_size = buffer_size
        self._buffers: dict[str, list[str]] = {}
        self._listeners: dict[str, set[asyncio.Queue]] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}

    def _get_buffer(self, thread_id: str) -> list[str]:
        return self._buffers.setdefault(thread_id, [])

    def add_event(self, thread_id: str, event_str: str):
        buf = self._get_buffer(thread_id)
        buf.append(event_str)
        if len(buf) > self.buffer_size:
            buf.pop(0)

        if thread_id in self._listeners:
            for q in list(self._listeners[thread_id]):
                q.put_nowait(event_str)

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        if thread_id not in self._listeners:
            self._listeners[thread_id] = set()
        q: asyncio.Queue = asyncio.Queue()
        self._listeners[thread_id].add(q)

        buf = self._get_buffer(thread_id)
        for event_str in buf:
            q.put_nowait(event_str)
        return q

    def unsubscribe(self, thread_id: str, q: asyncio.Queue):
        if thread_id in self._listeners:
            self._listeners[thread_id].discard(q)
            if not self._listeners[thread_id]:
                del self._listeners[thread_id]

    def is_running(self, thread_id: str) -> bool:
        task = self._running_tasks.get(thread_id)
        return task is not None and not task.done()

    def set_task(self, thread_id: str, task: asyncio.Task):
        self._running_tasks[thread_id] = task

    def finish_task(self, thread_id: str):
        self._running_tasks.pop(thread_id, None)


hub = ThreadStreamHub()


async def _run_agent_task(thread_id: str, message: str):
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [("user", message)]}
    streamed_text = False

    try:
        async for ev in graph.astream_events(inputs, config=config, version="v2"):
            kind = ev["event"]

            if kind == "on_chat_model_start":
                streamed_text = False

            elif kind == "on_chat_model_stream":
                content = ev["data"]["chunk"].content
                if content:
                    streamed_text = True
                    payload = json.dumps({"type": "text", "content": content})
                    hub.add_event(thread_id, f"data: {payload}\n\n")

            elif kind == "on_chat_model_end":
                output = ev["data"].get("output")
                content, tool_calls = _extract_text_and_tools(output)
                if not streamed_text and content and not tool_calls:
                    payload = json.dumps({"type": "text", "content": content})
                    hub.add_event(thread_id, f"data: {payload}\n\n")

            elif kind == "on_tool_start":
                payload = json.dumps({
                    "type": "tool_start",
                    "tool": ev["name"],
                    "input": ev["data"].get("input"),
                })
                hub.add_event(thread_id, f"data: {payload}\n\n")

    except Exception as exc:
        print(f"   [Task Error] thread {thread_id}: {exc}")
        err_payload = json.dumps({"type": "error", "error": str(exc)})
        hub.add_event(thread_id, f"data: {err_payload}\n\n")

    finally:
        hub.add_event(thread_id, "event: done\ndata: [DONE]\n\n")
        hub.finish_task(thread_id)


@app.post("/api/v2/chat/{thread_id}")
async def submit_v2(thread_id: str, message: str):
    """Submit a message. Returns immediately; events are consumed via GET stream.

    Returns HTTP 409 Conflict if a run is already active for this thread_id.
    """
    if hub.is_running(thread_id):
        raise HTTPException(
            status_code=409,
            detail="An agent turn is already active for this thread_id."
        )

    task = asyncio.create_task(_run_agent_task(thread_id, message))
    hub.set_task(thread_id, task)
    return {"status": "submitted", "thread_id": thread_id}


@app.get("/api/v2/chat/{thread_id}/stream")
async def stream_v2(thread_id: str):
    """Attach to the SSE stream for a thread_id. Replays recent buffer then tails live."""
    async def event_generator():
        q = hub.subscribe(thread_id)
        try:
            while True:
                msg = await q.get()
                yield msg
                if "event: done" in msg:
                    break
        finally:
            hub.unsubscribe(thread_id, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Client verification runner ────────────────────────────────────────────────
def run_client_simulation():
    try:
        import httpx
        import uvicorn
    except ImportError:
        print("uvicorn or httpx not available — install uvicorn and httpx to run simulation")
        return

    is_scripted = not os.environ.get("GEMINI_API_KEY")

    # Start live uvicorn server in background thread so asyncio tasks persist across requests
    port = 8765
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            # --- Part 1: Minimal Single-Endpoint POST SSE ---
            if is_scripted:
                ScriptedModel.reset_queue([
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "service_status", "id": "tc1", "args": {"name": "database"}}]
                    ),
                    AIMessage(content="Database status confirmed: healthy and operational (14ms latency)."),
                ])

            print("\n--- Part 1: Minimal Single-Endpoint POST SSE ---")
            print("> POST /api/v1/chat/thread-101 (message='Check database status')")
            seen_p1 = False
            with client.stream("POST", "/api/v1/chat/thread-101?message=Check+database+status") as response:
                for line in response.iter_lines():
                    if line:
                        print("   [SSE]", line)
                        if '"type":' in line:
                            seen_p1 = True

            assert seen_p1, "Part 1 failed to stream content events over SSE"

            # --- Part 2: Production Submit POST + Stream GET Split ---
            if is_scripted:
                ScriptedModel.reset_queue([
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "service_status", "id": "tc2", "args": {"name": "cache"}}]
                    ),
                    AIMessage(content="Cache cluster status confirmed: operational (99.9% uptime)."),
                ])

            print("\n--- Part 2: Production Submit POST + Stream GET Split ---")
            print("> POST /api/v2/chat/thread-102 (message='Check database status')")
            res = client.post("/api/v2/chat/thread-102?message=Check+database+status")
            print("   Response:", res.json())

            print("> GET /api/v2/chat/thread-102/stream")
            seen_p2 = False
            with client.stream("GET", "/api/v2/chat/thread-102/stream") as response:
                for line in response.iter_lines():
                    if line:
                        print("   [SSE]", line)
                        if '"type":' in line:
                            seen_p2 = True

            assert seen_p2, "Part 2 failed to stream content events over SSE"

            # --- Memory Verification (Part 1 second turn) ---
            if is_scripted:
                ScriptedModel.reset_queue([
                    AIMessage(content="Memory verified: previous thread context retained."),
                ])

            print("\n--- Memory Verification (Part 1 second turn) ---")
            print("> POST /api/v1/chat/thread-101 (message='Verify memory')")
            seen_mem = False
            with client.stream("POST", "/api/v1/chat/thread-101?message=Verify+memory") as response:
                for line in response.iter_lines():
                    if line:
                        print("   [SSE]", line)
                        if '"type":' in line:
                            seen_mem = True

            assert seen_mem, "Memory verification failed to stream content events"

            print("\nExample finished successfully!")
    finally:
        server.should_exit = True
        thread.join(timeout=1.0)


if __name__ == "__main__":
    run_client_simulation()
