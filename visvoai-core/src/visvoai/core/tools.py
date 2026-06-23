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
from typing import Any, ClassVar, Dict, List, Optional, Set, Type, get_type_hints

from pydantic import BaseModel, ConfigDict, create_model

from visvoai.core.persistence import ToolPersistence

logger = logging.getLogger(__name__)


class ToolConfig:
    """The single declaration of generic tool metadata — caching, routing, and
    scheduling hints. `BaseAgentTool` inherits these as ordinary class attributes
    (so `tool.is_core` reads the default directly), and `@tool_config` validates
    kwargs against them. There is no separate hand-maintained schema.

    Platform-specific axes — roles (auth), approval (HITL), UI metadata (canvas),
    background execution — live in the platform's `ToolMeta`, which SUBCLASSES this
    (see backend/tools/base.py).

    This is a plain class, NOT a pydantic model, precisely so the fields are
    inheritable as readable class attributes. Import-time validation/coercion is
    provided by a pydantic model derived from these annotations via
    `build_config_validator()`.
    """
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


def build_config_validator(config_cls: type) -> Type[BaseModel]:
    """Derive a pydantic validator from a config class's annotated fields.

    The config class (`ToolConfig`, or the platform's `ToolMeta`) is the single
    source of field declarations. This builds a throwaway pydantic model from it
    so `@tool_config` can coerce + validate kwargs at import time without a second
    schema that could drift. Call once per config class and cache the result.
    """
    fields: Dict[str, Any] = {}
    for fname, ftype in get_type_hints(config_cls).items():
        if fname.startswith("_"):
            continue
        fields[fname] = (ftype, getattr(config_cls, fname, ...))
    return create_model(
        f"{config_cls.__name__}Validator",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **fields,
    )


_CONFIG_VALIDATOR: Type[BaseModel] = build_config_validator(ToolConfig)


def tool_config(**kwargs: Any):
    """Decorator — declares tool metadata, validated/coerced at import time.

    Sets only the fields passed; everything else inherits its `ToolConfig` default
    via `BaseAgentTool`. Coercion runs through a pydantic model derived from
    `ToolConfig`, so e.g. `@tool_config(is_core="yes")` sets the bool `True`.

    Usage:
        @tool_config(is_core=True, routing_hint="Use when the user asks to...")
        class MyTool(BaseAgentTool):
            ...
    """
    validated = _CONFIG_VALIDATOR(**kwargs)

    def decorator(cls: type) -> type:
        for key in kwargs:
            setattr(cls, key, getattr(validated, key, kwargs[key]))
        return cls

    return decorator


class BaseAgentTool(ToolConfig, ABC):
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

    # ── Config defaults ───────────────────────────────────────
    # The 13 generic config fields (is_core, no_cache, …) are inherited from
    # ToolConfig — the single source. @tool_config overrides them per class.

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
