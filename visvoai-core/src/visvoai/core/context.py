"""
visvoai.core.context — Surface-agnostic orchestrator state.

RuntimeContext is the only context type that visvoai-core tools receive. A
surface that needs more (auth, a datastore session, streaming handles) extends
it with its own dataclass subclass and passes that to its tools instead.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeContext:
    """
    Surface-agnostic orchestrator state passed to tools.

    Contains only fields that make sense on any surface (CLI, server, tests).
    No auth, no datastore, no HTTP concerns. Surface- or plugin-specific state
    (e.g. plan-mode or skill bookkeeping) is NOT here — a subclass adds it.

    Surfaces subclass this and add their own fields, for example:
      CLIContext(RuntimeContext) — a CLI surface (cwd, terminal_width)
    """
    request_id: Optional[str] = None
    subagent_depth: int = 0
    parent_tool_call_id: Optional[str] = None
