"""
visvoai.cli.hitl_modes — graduated approval modes for the permission gate.

The gate (agent_turn._approve) reads the active mode to decide whether to prompt:

  NORMAL      ask before every mutating tool (edit/write/shell)
  AUTO_EDIT   auto-approve file edits (edit_file/write_file); still ask on run_shell
  ACCEPT_ALL  auto-approve everything (the real "yolo")

The mode relaxes APPROVAL only. Path confinement lives in the tools, not the gate,
so even ACCEPT_ALL cannot write outside the allowed roots or into .git — the
boundary is never relaxed by a mode. Modes are session-only (reset to NORMAL on
launch); cycled by shift+tab or /mode.
"""
from __future__ import annotations

from enum import Enum

# Tools AUTO_EDIT auto-approves (file mutations). run_shell is deliberately absent —
# it stays gated until ACCEPT_ALL.
_AUTO_EDIT_TOOLS = frozenset({"edit_file", "write_file"})


class HITLMode(Enum):
    NORMAL = "normal"
    AUTO_EDIT = "auto-edit"
    ACCEPT_ALL = "accept-all"

    @property
    def label(self) -> str:
        return self.value

    @property
    def chip(self) -> str | None:
        """The status-bar chip text — None in NORMAL (no chip, no clutter)."""
        return None if self is HITLMode.NORMAL else self.value

    def next(self) -> "HITLMode":
        order = list(HITLMode)
        return order[(order.index(self) + 1) % len(order)]

    def auto_approves(self, tool_name: str) -> bool:
        """True if this mode pre-approves `tool_name` without prompting."""
        if self is HITLMode.ACCEPT_ALL:
            return True
        if self is HITLMode.AUTO_EDIT:
            return tool_name in _AUTO_EDIT_TOOLS
        return False
