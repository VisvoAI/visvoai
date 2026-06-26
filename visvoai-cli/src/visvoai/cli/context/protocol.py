"""
visvoai.cli.context.protocol — the context-provider contract.

A ContextProvider renders one section of the system prompt. The ContextAssembler
runs an ordered set of them each turn (see assembler.py). Two cadences:

  static   — rendered ONCE and cached for the session (the cacheable prefix)
  per_turn — re-rendered every turn (the volatile suffix)

Providers carry their own config (enabled / order / budget). The config layer
(config.py) mutates those instance attributes; the assembler never reads config.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Cadence = Literal["static", "per_turn"]


@dataclass(frozen=True)
class ContextSection:
    """One provider's rendered, budget-clipped contribution to the prompt."""
    name: str
    content: str
    order: int


class ContextProvider:
    """Base class for a context provider — one section of the assembled prompt.

    Subclasses set the class attributes and implement `render`. Defaults live on
    the class; per-instance `enabled` / `order` / `budget_tokens` start from the
    defaults and may be overridden by the config layer after construction.
    """

    name: str = ""
    cadence: Cadence = "static"
    default_order: int = 100
    default_budget_tokens: int = 2000

    def __init__(self) -> None:
        self.enabled: bool = True
        self.order: int = self.default_order
        self.budget_tokens: int = self.default_budget_tokens

    def render(self, state: dict) -> Optional[str]:
        """Return this section's text, or None to contribute nothing this turn.

        `state` is the LangGraph AgentState for the current turn (carries
        `messages`); most providers ignore it. Must never raise — a provider
        that can't render returns None so the turn proceeds without its section.
        """
        raise NotImplementedError
