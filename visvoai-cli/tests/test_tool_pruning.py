"""Tool-result management: old/large tool results are elided (to a stub, id preserved)
when building the model input, keeping recent ones verbatim within a char budget.
Transforms only the sent copy — never the durable thread."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from visvoai.cli import agent_turn
from visvoai.cli.agent_turn import (
    MIN_ELIDE_CHARS, TOOL_RESULT_BUDGET_CHARS, _prune_tool_results,
)


def _tool(id, n):
    return ToolMessage(content="x" * n, tool_call_id=id, name="read_file")


def test_within_budget_is_untouched():
    msgs = [HumanMessage(content="q"), _tool("a", 100), _tool("b", 200)]
    out, n = _prune_tool_results(msgs)
    assert n == 0 and out is msgs


def test_old_large_results_elided_recent_kept():
    big = TOOL_RESULT_BUDGET_CHARS + 5_000
    msgs = [
        _tool("old", big),      # oldest, big → should be elided
        HumanMessage(content="next"),
        _tool("recent", big),   # newest, big → kept (fills the budget)
    ]
    out, n = _prune_tool_results(msgs)
    assert n == 1
    # recent kept verbatim
    assert out[2].content == "x" * big and out[2].tool_call_id == "recent"
    # old elided to a stub, but tool_call_id preserved (pairing stays valid)
    assert "elided" in out[0].content and out[0].tool_call_id == "old"
    assert len(out[0].content) < big


def test_small_old_results_not_worth_eliding():
    big = TOOL_RESULT_BUDGET_CHARS + 1
    small = MIN_ELIDE_CHARS - 1
    msgs = [_tool("tiny_old", small), _tool("recent", big)]
    out, n = _prune_tool_results(msgs)
    assert n == 0                       # tiny old one left alone (not worth a stub)


def test_non_tool_messages_pass_through():
    big = TOOL_RESULT_BUDGET_CHARS + 1
    ai = AIMessage(content="answer")
    msgs = [_tool("old", big), ai, _tool("recent", big)]
    out, _ = _prune_tool_results(msgs)
    assert out[1] is ai                 # AIMessage untouched, order preserved


def test_durable_history_untouched_marker():
    # _prune_tool_results returns a NEW list on elision; the input is not mutated.
    big = TOOL_RESULT_BUDGET_CHARS + 1
    original = _tool("old", big)
    msgs = [original, _tool("recent", big)]
    out, n = _prune_tool_results(msgs)
    assert n == 1
    assert original.content == "x" * big   # original object unchanged
    assert out[0] is not original          # stub is a new object
