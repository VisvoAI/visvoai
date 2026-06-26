"""Conversation alignment grid — the single source of truth for column layout.

Every conversation block follows ONE grid (unified-grid model, decided 2026-06-24):
a left margin, a fixed-width gutter holding the block's marker glyph, then content
at a constant column. Markers align vertically in the gutter; ALL content aligns
at `CONTENT`.

    col:  0        1 . 2        3 ...........................
          margin   gutter       content
          ' '      'glyph '     text…………………………………………………

How widgets honour it:
- Text-render blocks (Thinking, ToolRow, SystemNote, ErrorBlock, PlanStep, …)
  prepend `gutter(glyph, style)` in render() and set CSS `padding-left: MARGIN`.
  → glyph at col MARGIN, content at col CONTENT.
- Blank-gutter blocks (the answer / tool bodies: Assistant, ToolOutput, CleanDiff)
  carry no glyph and set CSS `padding-left: CONTENT`. → content at col CONTENT.
- Multi-line content continues at col CONTENT (prefix continuation with `INDENT`).
- Nested sub-items (plan steps) sit at `SUBITEM`.

These are the ONLY indentation numbers in the conversation. Change them here.
"""
from __future__ import annotations

from rich.text import Text

MARGIN = 1                  # left margin; CSS padding-left for gutter blocks
GUTTER = 2                  # marker glyph + trailing space
CONTENT = MARGIN + GUTTER   # 3 — content column; padding-left for blank-gutter blocks
SUBITEM = CONTENT + 2       # 5 — nested sub-items (e.g. plan steps)
INDENT = " " * GUTTER       # prefix for continuation lines to reach CONTENT


def gutter(glyph: str, style: str = "") -> Text:
    """The block's 2-cell gutter: a 1-cell marker glyph + a trailing space.
    Pass a single space as `glyph` for a blank gutter that still aligns content."""
    return Text(f"{glyph} ", style=style)
