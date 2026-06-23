"""Lifecycle tests for BaseAgentTool.execute() — the default override-seam body.

A streaming consumer may override execute() wholesale, so these tests pin the
default body's contract for the consumers that inherit it as-is (the CLI surface,
external tools):

  - on_start fires before _execute, on_complete fires after, in order
  - the id returned by on_start is the one threaded into _execute
  - a raising _execute triggers on_error (not on_complete) and re-raises
"""
from typing import Any, ClassVar, List, Optional

from pydantic import BaseModel

from visvoai.core.persistence import ToolPersistence
from visvoai.core.tools import BaseAgentTool, tool_config


class RecordingPersistence(ToolPersistence):
    """Records lifecycle calls in order and rewrites the tool_id on start."""

    REWRITTEN_ID = "persisted-id"

    def __init__(self) -> None:
        self.events: List[tuple] = []

    def on_start(self, *, tool_id: str, tool_name: str, tool_input: dict, **kwargs: Any) -> str:
        self.events.append(("start", tool_name, tool_input))
        return self.REWRITTEN_ID

    def on_complete(self, *, tool_id: str, status: str, output: dict, duration_ms: int, **kwargs: Any) -> None:
        self.events.append(("complete", tool_id, status))

    def on_error(self, *, tool_id: str, error: str, duration_ms: int) -> None:
        self.events.append(("error", tool_id, error))


class _Args(BaseModel):
    text: str = ""


@tool_config(is_core=True)
class _EchoTool(BaseAgentTool):
    name = "echo_test"
    description = "Echo the input back."
    args_schema = _Args
    _owned_resource_checks: ClassVar[Optional[List[Any]]] = []

    def _execute(self, tool_call_id: str, **kwargs: Any) -> Any:
        return {"output": kwargs.get("text", ""), "seen_id": tool_call_id}


@tool_config(is_core=True)
class _BoomTool(BaseAgentTool):
    name = "boom_test"
    description = "Always raises."
    args_schema = _Args
    _owned_resource_checks: ClassVar[Optional[List[Any]]] = []

    def _execute(self, tool_call_id: str, **kwargs: Any) -> Any:
        raise RuntimeError("kaboom")


def test_success_fires_start_then_complete():
    tool = _EchoTool()
    rec = RecordingPersistence()
    tool._persistence = rec

    result = tool.execute(tool_call_id="caller-id", text="hi")

    assert result["output"] == "hi"
    # on_start's returned id is threaded into _execute, not the caller's id.
    assert result["seen_id"] == RecordingPersistence.REWRITTEN_ID
    assert [e[0] for e in rec.events] == ["start", "complete"]
    assert rec.events[1] == ("complete", RecordingPersistence.REWRITTEN_ID, "SUCCESS")
    # Private kwargs are stripped from the persisted input.
    assert rec.events[0][2] == {"text": "hi"}


def test_failure_fires_error_and_reraises():
    tool = _BoomTool()
    rec = RecordingPersistence()
    tool._persistence = rec

    try:
        tool.execute(text="x")
        raised = False
    except RuntimeError as exc:
        raised = str(exc) == "kaboom"

    assert raised, "execute() must re-raise the original exception"
    assert [e[0] for e in rec.events] == ["start", "error"]
    assert rec.events[1] == ("error", RecordingPersistence.REWRITTEN_ID, "kaboom")
