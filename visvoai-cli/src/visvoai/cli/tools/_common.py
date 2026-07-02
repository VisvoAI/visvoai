"""Shared output-bounding helpers for the CLI tools.

Every tool caps its result so a single call can't flood the model's context (and
the per-turn token cost). These are the primitives the file/shell/web tools share.
"""
MAX_LINE_LEN = 2000      # over-long lines are clipped (one line ≠ a whole file)


def clip_line(s: str) -> str:
    return s if len(s) <= MAX_LINE_LEN else s[:MAX_LINE_LEN] + " …[line truncated]"


def as_text(v) -> str:
    """Coerce subprocess output to str. TimeoutExpired.stdout/.stderr are BYTES
    even when the run used text=True (Python quirk) — decoding defensively here
    keeps a timeout from raising TypeError inside the handler."""
    if isinstance(v, bytes):
        return v.decode(errors="replace")
    return v or ""


def cap_lines(text: str, max_lines: int) -> str:
    """Return text limited to max_lines, with a marker noting how many were dropped."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + (
        f"\n…[output truncated: showing {max_lines} of {len(lines)} lines]")
