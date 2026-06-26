"""Token-usage extraction — one place that reads LangChain `usage_metadata`.

Every LangChain chat message/stream chunk carries `usage_metadata` (input/output/
total token counts) when the provider reports it. Centralising the read here means
consumers (CLI cost/context tracking, future platform reuse) don't each re-derive
the shape. Cache-token detail is intentionally NOT surfaced yet (provider-reporting
is inconsistent in the streaming path — deferred with accurate cache pricing).
"""
from __future__ import annotations

from typing import Any


def usage_from(message_or_chunk: Any) -> dict:
    """{'input', 'output', 'total'} token counts from a message/chunk's
    usage_metadata, all 0 when absent. Sum these across a turn's model calls."""
    u = getattr(message_or_chunk, "usage_metadata", None) or {}
    return {
        "input": int(u.get("input_tokens") or 0),
        "output": int(u.get("output_tokens") or 0),
        "total": int(u.get("total_tokens") or 0),
    }
