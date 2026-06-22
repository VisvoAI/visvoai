"""
visvoai.core.persistence — ToolPersistence interface.

The default implementation is a no-op. Platform surfaces inject a concrete
implementation via tool_instance._persistence before execution:

  tool_instance._persistence = MyPersistence()

Web platform: HistoryManagerPersistence writes lifecycle events to PostgreSQL.
CLI surface:  ToolPersistence() (the default) — no writes, just returns IDs.
"""
from typing import Any, Optional


class ToolPersistence:
    """
    Lifecycle hooks for tool call tracking.

    The default implementation is a no-op: returns provided IDs unchanged and
    persists nothing. Platform surfaces inject a concrete subclass via
    tool_instance._persistence so DB writes happen only on that surface.
    """

    def on_start(
        self,
        *,
        tool_id: str,
        message_id: str,
        tool_name: str,
        tool_input: dict,
        agent_step: int,
        execution_phase: Optional[str],
        parent_id: Optional[str],
        is_skill: bool,
        display_name: Optional[str],
        generation_started_at: Optional[Any],
    ) -> str:
        """Called before tool execution begins. Returns the canonical tool_call_id."""
        return tool_id

    def on_resume(self, tool_id: str) -> str:
        """Called on checkpoint resume. Transitions existing row to IN_PROGRESS."""
        return tool_id

    def on_complete(
        self,
        *,
        tool_id: str,
        status: str,
        output: dict,
        duration_ms: int,
        display_name: Optional[str],
    ) -> None:
        """Called on tool completion (any terminal status)."""
        pass

    def on_error(
        self,
        *,
        tool_id: str,
        error: str,
        duration_ms: int,
    ) -> None:
        """Called when tool raises an unexpected exception."""
        pass
