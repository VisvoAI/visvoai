"""
visvoai.core.tools — Public tool base class and registry.

External developers subclass BaseAgentTool to build tools that work with
AgentRuntime / CLIRuntime. Tools auto-register at class definition time.

Usage:
    from visvoai.core.tools import BaseAgentTool, tool_config

    @tool_config(is_core=True, routing_hint="Use for...")
    class MyTool(BaseAgentTool):
        name = "my_tool"
        description = "Does something useful."
        args_schema = MyToolArgs

        _owned_resource_checks: ClassVar[list] = []  # no checks

        def _execute(self, tool_call_id: str, **kwargs):
            # your logic here
            return ToolResult(tool_name=self.name, ...)
"""
from __future__ import annotations

import uuid
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional, Set, Type

from pydantic import BaseModel, ConfigDict

from visvoai.core.persistence import ToolPersistence

logger = logging.getLogger(__name__)


class ToolConfig(BaseModel):
    """Generic tool metadata declared on a tool class via @tool_config.

    These are the surface-agnostic agent concerns (caching, routing, scheduling
    hints). Platform-specific axes — roles (auth), approval (HITL), UI metadata
    (canvas), background execution — live in the platform's `ToolMeta`, which
    SUBCLASSES this (see backend/tools/base.py).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_core: bool = False
    no_cache: bool = False
    cache_key_args: Optional[List[str]] = None
    routing_hint: Optional[str] = None
    anti_patterns: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None
    parallel_with: Optional[List[str]] = None
    skip_context_chunk: bool = False
    persist_context: bool = False
    sequential_only: bool = False
    idempotent: bool = True
    deprecated: bool = False
    disabled: bool = False


def tool_config(**kwargs: Any):
    """Decorator — declares tool metadata. Validated at import time.

    Usage:
        @tool_config(is_core=True, routing_hint="Use when the user asks to...")
        class MyTool(BaseAgentTool):
            ...
    """
    config = ToolConfig(**kwargs)

    def decorator(cls: type) -> type:
        for field_name in ToolConfig.model_fields:
            setattr(cls, field_name, getattr(config, field_name))
        return cls

    return decorator


class BaseAgentTool(ABC):
    """
    Abstract base for public visvoai-core tools.

    Subclass this to build tools that work with AgentRuntime and CLIRuntime.
    Tools auto-register at definition time — no manual registration needed.

    Minimal concrete subclass:
        @tool_config(is_core=True)
        class EchoTool(BaseAgentTool):
            name = "echo"
            description = "Echo the input back."
            args_schema = EchoArgs
            _owned_resource_checks: ClassVar[list] = []

            def _execute(self, tool_call_id: str, **kwargs):
                return {"output": kwargs.get("text", "")}

    The _persistence class attribute is replaced at runtime by the surface
    (platform injects HistoryManagerPersistence; CLI keeps the no-op default).
    """

    # ── Identity ──────────────────────────────────────────────
    name: str
    description: str
    args_schema: Type[BaseModel]
    llm_schema: Optional[Type[BaseModel]] = None  # exposed to LLM; defaults to args_schema

    # ── Config defaults (overridden by @tool_config) ──────────
    is_core: bool = False
    no_cache: bool = False
    cache_key_args: Optional[List[str]] = None
    skip_context_chunk: bool = False
    persist_context: bool = False
    routing_hint: Optional[str] = None
    anti_patterns: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None
    parallel_with: Optional[List[str]] = None
    sequential_only: bool = False
    idempotent: bool = True
    deprecated: bool = False
    disabled: bool = False

    # ── Resource access declarations (declare [] in concrete classes) ─────
    _owned_resource_checks: ClassVar[Optional[List[Any]]] = None

    # ── Persistence (injected by surface layer) ───────────────
    _persistence: ToolPersistence = ToolPersistence()

    # ── Auto-registration ─────────────────────────────────────
    _registry: ClassVar[List[Type[BaseAgentTool]]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Register only fully concrete classes (not intermediate ABCs)
        if not getattr(cls, "__abstractmethods__", None) and getattr(cls, "name", None):
            BaseAgentTool._registry.append(cls)

    @abstractmethod
    def _execute(self, tool_call_id: str, **kwargs: Any) -> Any:
        """Execute the tool's logic. Return a result dict or ToolResult."""

    def execute(
        self,
        tool_call_id: Optional[str] = None,
        agent_step: int = 0,
        execution_phase: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute the tool with persistence lifecycle tracking.

        Calls _persistence.on_start(), _execute(), and _persistence.on_complete()
        (or _persistence.on_error() on exception). Returns whatever _execute() returns.
        """
        start = time.time()
        effective_id = tool_call_id or str(uuid.uuid4())

        pre_id = self._persistence.on_start(
            tool_id=effective_id,
            message_id="",
            tool_name=self.name,
            tool_input={k: v for k, v in kwargs.items() if not k.startswith("_")},
            agent_step=agent_step,
            execution_phase=execution_phase,
            parent_id=None,
            is_skill=False,
            display_name=None,
            generation_started_at=None,
        )
        try:
            result = self._execute(tool_call_id=pre_id, **kwargs)
            duration_ms = int((time.time() - start) * 1000)
            status = getattr(getattr(result, "status", None), "value", "SUCCESS")
            self._persistence.on_complete(
                tool_id=pre_id,
                status=status,
                output=result if isinstance(result, dict) else {},
                duration_ms=duration_ms,
                display_name=None,
            )
            return result
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            self._persistence.on_error(
                tool_id=pre_id,
                error=str(exc),
                duration_ms=duration_ms,
            )
            raise
