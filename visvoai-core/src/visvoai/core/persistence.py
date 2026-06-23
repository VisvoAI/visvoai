"""
visvoai.core.persistence — ToolPersistence and LLMPersistence interfaces.

The default implementation is a no-op. A surface that wants to record tool calls
injects a concrete subclass via tool_instance._persistence before execution:

  tool_instance._persistence = MyPersistence()

Out of the box the no-op default just returns IDs and writes nothing, so tools
run standalone with no datastore. Subclass on_start/on_complete/on_error to send
lifecycle events wherever you keep them.
"""
from typing import Any, Optional


class ToolPersistence:
    """
    Lifecycle hooks for tool call tracking.

    The default implementation is a no-op: returns provided IDs unchanged and
    persists nothing. A surface injects a concrete subclass via
    tool_instance._persistence so recording happens only where it's wanted.
    """

    def on_start(
        self,
        *,
        tool_id: str,
        message_id: str,
        tool_name: str,
        tool_input: dict,
        agent_step: int,
        execution_phase: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Called before tool execution begins. Returns the canonical tool_call_id.
        **kwargs: a subclass may accept extra surface-specific fields here."""
        return tool_id

    def on_resume(self, tool_id: str) -> str:
        """Called on checkpoint resume. Transitions an existing record to in-progress."""
        return tool_id

    def on_complete(
        self,
        *,
        tool_id: str,
        status: str,
        output: dict,
        duration_ms: int,
        **kwargs: Any,
    ) -> None:
        """Called on tool completion (any terminal status).
        **kwargs: a subclass may accept extra surface-specific fields here."""
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


class LLMPersistence:
    """
    Lifecycle hooks for LLM call tracking.

    The default implementation is a no-op. Inject a concrete subclass to record
    cost/token accounting wherever you want it; standalone it stays silent.

    All methods use keyword-only args so new fields can be added without
    breaking existing subclasses that don't care about them.
    """

    def on_call_complete(
        self,
        *,
        message_id: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        action: str,
        estimated_cost_usd: str,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Called once per turn when LLM call stats are ready to persist."""
        pass

    def on_thinking_log(
        self,
        *,
        message_id: str,
        thinking_text: str,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Called for each thinking block emitted by the model."""
        pass
