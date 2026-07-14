"""Seam guard: langchain imports stay confined to the declared boundary files.

The standing decision (2026-07): keep langchain/langgraph, but keep the door
open — LC types must not spread into widgets/screens/app code, so a future
migration stays a bounded project instead of a rewrite. This test is the
mechanical version of that rule, same spirit as scripts/check_package_boundary.

If you legitimately need LC in a new module, that's an architecture decision:
extend the seam deliberately (add it here WITH a reason), don't just import.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "visvoai" / "cli"

# module path (relative to src/visvoai/cli) → why it may import langchain
ALLOWED = {
    "agent.py":              "graph glue + stream chunk extractors",
    "agent_turn.py":         "consumes astream_events + message types (until C-split)",
    "agents.py":             "run_agent StructuredTool + InjectedToolCallId",
    "commands.py":           "message types for /compact history slicing",
    "context/assembler.py":  "SystemMessage assembly",
    "gated_tools.py":        "BaseTool wrapping (the gate layer)",
    "main.py":               "headless single-shot loop",
    "mcp.py":                "langchain-mcp-adapters",
    "rewind.py":             "message types for thread slicing",
    "runtime.py":            "core AgentRuntime override",
    "skills.py":             "read_skill StructuredTool",
    "store.py":              "message (de)serialization — the persistence seam",
    "toolkit.py":            "the public tool contract",
    "tools/__init__.py":     "tool aggregation",
    "tools/background.py":   "tool defs",
    "tools/files.py":        "tool defs",
    "tools/shell.py":        "tool defs",
    "tools/web.py":          "tool defs",
}

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(langchain|langgraph)", re.MULTILINE)


def test_langchain_imports_only_in_declared_seams():
    violations = []
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if _IMPORT_RE.search(path.read_text(encoding="utf-8")):
            if rel not in ALLOWED:
                violations.append(rel)
    assert not violations, (
        f"langchain/langgraph imported outside the declared seams: {violations}. "
        "Widgets/screens/app code must stay LC-free — extend ALLOWED in "
        "tests/test_import_seams.py (with a reason) only as a deliberate "
        "architecture decision.")


def test_widgets_and_screens_are_lc_free():
    """The strong form for the UI layer specifically — no exceptions here."""
    for sub in ("widgets", "screens"):
        for path in (SRC / sub).rglob("*.py"):
            assert not _IMPORT_RE.search(path.read_text(encoding="utf-8")), (
                f"{path} imports langchain — UI renders plain data, never LC types")
