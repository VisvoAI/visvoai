"""
visvoai.cli.context.assembler — ContextAssembler: per-turn prompt composition.

Replaces the CLI's single static system prompt with an ordered set of providers
composed each turn. The assembled prompt is always:

    [ static block, sorted by order ]   ← rendered once, cached for the session
    [ per_turn block, sorted by order ] ← re-rendered every turn

Static always precedes volatile so the prefix stays byte-stable across turns —
that contiguous prefix is what providers' prompt caches can hit. `order` sorts
WITHIN each block, not across the boundary.

Budgeting is truncate-per-section: each section is clipped to its own
budget_tokens, and the joined prompt is clamped to a global budget as a backstop.
No LLM calls, no dropped sections — same philosophy as tools/_common.py.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .protocol import ContextProvider, ContextSection

# Reimplemented locally (not imported from visvoai.core.graph) to avoid coupling
# to a private symbol — these are the CLI's own copies of the core behaviour.
_FINALIZE_INSTRUCTION = (
    "[SYSTEM] You have reached the maximum number of tool-using steps for this turn. "
    "Do NOT attempt any further tool calls — they will not be available. Provide your "
    "best final answer now from the information you already have. If the task is "
    "incomplete, summarize what you found and state clearly what remains unresolved."
)

# Cheap token estimate — chars/4 — to avoid a tokenizer dependency. Budgets are
# coarse guardrails, not exact accounting, so the heuristic is sufficient.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


def clip_to_tokens(text: str, max_tokens: Optional[int]) -> str:
    """Clip text to ~max_tokens, on a line boundary when possible, marking the cut.
    None/<=0 budget means no clipping."""
    if not max_tokens or max_tokens <= 0:
        return text
    limit = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    head = text[:limit]
    nl = head.rfind("\n")
    if nl > limit // 2:  # only snap to a newline if it doesn't waste half the budget
        head = head[:nl]
    return head.rstrip() + "\n… [truncated to fit context budget]"


def rounds_this_turn(messages: Sequence[BaseMessage]) -> int:
    """Agent (AIMessage) rounds since the last human message — the turn's depth.
    Local copy of the core helper; drives the soft-step-cap forced-finalize."""
    n = 0
    for m in reversed(list(messages)):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage):
            n += 1
    return n


class ContextAssembler:
    """Composes the per-turn system prompt from its providers.

    cwd is held by the providers themselves (constructed with it), not by the
    assembler — GraphBuildContext carries no cwd, so the runtime hands cwd to the
    providers at build time.
    """

    def __init__(
        self,
        providers: Sequence[ContextProvider],
        *,
        global_budget_tokens: int = 8000,
    ) -> None:
        self._providers: List[ContextProvider] = [p for p in providers if p.enabled]
        self._global_budget = global_budget_tokens
        self._static_cache: Optional[List[ContextSection]] = None

    def _render(self, provider: ContextProvider, state: dict) -> Optional[ContextSection]:
        """Render one provider, swallowing any failure (a broken provider must not
        kill the turn) and clipping to its per-section budget."""
        try:
            text = provider.render(state)
        except Exception:
            return None
        if not text or not text.strip():
            return None
        clipped = clip_to_tokens(text.strip(), provider.budget_tokens)
        return ContextSection(name=provider.name, content=clipped, order=provider.order)

    def _static_sections(self, state: dict) -> List[ContextSection]:
        if self._static_cache is None:
            rendered = [
                self._render(p, state)
                for p in self._providers
                if p.cadence == "static"
            ]
            self._static_cache = sorted(
                (s for s in rendered if s is not None), key=lambda s: s.order
            )
        return self._static_cache

    def _per_turn_sections(self, state: dict) -> List[ContextSection]:
        rendered = [
            self._render(p, state)
            for p in self._providers
            if p.cadence == "per_turn"
        ]
        return sorted((s for s in rendered if s is not None), key=lambda s: s.order)

    def assemble(self, state: dict, *, finalize: bool = False) -> str:
        """Build the full system prompt for this turn. `finalize` appends the
        forced-finalize instruction (soft step cap reached) as the last section."""
        sections = self._static_sections(state) + self._per_turn_sections(state)
        parts = [s.content for s in sections]
        if finalize:
            parts.append(_FINALIZE_INSTRUCTION)
        full = "\n\n".join(p for p in parts if p)
        return clip_to_tokens(full, self._global_budget)
