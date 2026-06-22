"""
visvoai.core.context — Surface-agnostic orchestrator state.

RuntimeContext is the only context type that public visvoai-core tools receive.
Platform surfaces (web, IDE) extend it with their own dataclass subclass
(e.g. BackendContext in visvo-platform adds auth, DB, and streaming fields).
"""
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeContext:
    """
    Surface-agnostic orchestrator state passed to tools.

    Contains only fields that make sense on any surface (CLI, web, tests).
    No auth, no DB, no HTTP concerns.

    Platform extensions subclass this and add surface-specific fields:
      BackendContext(RuntimeContext) — web platform (auth, streaming, DB registries)
      CLIContext(RuntimeContext)     — CLI surface (cwd, terminal_width)
    """
    request_id: Optional[str] = None
    subagent_depth: int = 0
    plan_state_ref: Optional[dict] = None
    plan_lock: Optional[threading.Lock] = None
    parent_tool_call_id: Optional[str] = None
    # Active skill's supporting files — maps filename → file content string.
    active_skill_resources: Optional[dict] = None
    # ID of the currently active prompt-injection skill tool call (UUID).
    active_skill_id: Optional[str] = None
