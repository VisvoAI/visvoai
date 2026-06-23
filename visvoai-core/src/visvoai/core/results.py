"""
visvoai.core.results — the minimal tool-result envelope.

This is the lean core of what pi.dev calls AgentToolResult: a model-facing
`result` string plus a generic `data` bag (the canonical payload lives at
`data["output"]`), tagged with a basic execution `status`. Nothing here knows
about HITL, citations, canvas/artifacts, streaming, or the DB — those are
platform concerns that extend this envelope (see backend/models/query.py
`ToolResult`, which subclasses this and adds question/sources/artifacts, and
backend/models/enums.py `ToolStatus`, which adds the HITL statuses).

Core tools and external consumers return THIS. The platform widens it.
"""
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class ToolStatus(str, Enum):
    """Basic execution outcomes every tool can produce. HITL statuses
    (NEEDS_HITL/PENDING_HITL/REJECTED) are a platform extension — not here."""
    SUCCESS = "SUCCESS"
    EMPTY_RESULT = "EMPTY_RESULT"
    INVALID_INPUT = "INVALID_INPUT"
    TOOL_ERROR = "TOOL_ERROR"


class ToolResult(BaseModel):
    """Standardized return object for agent tools — the minimal envelope.

    Prefer the status factory classmethods over the raw constructor: they encode
    the output contract so the payload lands where consumers read it. The
    canonical payload field is `data["output"]`, mirrored to `result`.

    The platform subclass adds question/sources/artifacts; those default to None
    here and are absent for core/external tools.
    """
    model_config = ConfigDict(extra="ignore")

    tool_name: str
    status: ToolStatus
    result: str
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, tool_name: str, payload: str, display: Optional[str] = None, **meta: Any) -> "ToolResult":
        """SUCCESS — `payload` is the answer. Goes in `data["output"]` and `result`.
        `display` overrides GUI rendering only. `meta` adds structured metadata keys."""
        data: Dict[str, Any] = {"output": payload, **meta}
        if display is not None:
            data["display"] = display
        return cls(tool_name=tool_name, status=ToolStatus.SUCCESS, result=payload, data=data)

    @classmethod
    def invalid_input(cls, tool_name: str, whats_wrong: str, expected: Optional[str] = None) -> "ToolResult":
        """INVALID_INPUT — recoverable bad args shaped so the model self-corrects."""
        msg = whats_wrong if not expected else f"{whats_wrong}\n\nExpected: {expected}"
        return cls(tool_name=tool_name, status=ToolStatus.INVALID_INPUT, result=msg, data={"error": msg})

    @classmethod
    def tool_error(cls, tool_name: str, error: Any, **meta: Any) -> "ToolResult":
        """TOOL_ERROR — runtime/boundary failure. `meta` carries diagnostic keys."""
        msg = f"{tool_name}: {error}"
        return cls(tool_name=tool_name, status=ToolStatus.TOOL_ERROR, result=msg, data={"error": str(error), **meta})

    @classmethod
    def empty(cls, tool_name: str, reason: str, next_step: Optional[str] = None, **meta: Any) -> "ToolResult":
        """EMPTY_RESULT — succeeded but produced nothing. Always give a reason."""
        msg = reason if not next_step else f"{reason} {next_step}"
        return cls(tool_name=tool_name, status=ToolStatus.EMPTY_RESULT, result=msg, data={**meta})
