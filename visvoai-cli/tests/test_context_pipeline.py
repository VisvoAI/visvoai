"""The configurable context-assembly pipeline: assembler, providers, config."""
from __future__ import annotations

import os

from visvoai.cli.context import build_assembler
from visvoai.cli.context.assembler import (
    ContextAssembler,
    clip_to_tokens,
    estimate_tokens,
    rounds_this_turn,
)
from visvoai.cli.context.config import apply_to_providers, global_budget
from visvoai.cli.context.protocol import ContextProvider
from visvoai.cli.context.providers import (
    BasePromptProvider,
    DateTimeProvider,
    ProjectInstructionsProvider,
)


class _Static(ContextProvider):
    name = "s"
    cadence = "static"
    default_order = 5

    def __init__(self, text):
        super().__init__()
        self._text = text
        self.calls = 0

    def render(self, state):
        self.calls += 1
        return self._text


class _PerTurn(ContextProvider):
    name = "p"
    cadence = "per_turn"
    default_order = 50

    def __init__(self, text):
        super().__init__()
        self._text = text
        self.calls = 0

    def render(self, state):
        self.calls += 1
        return self._text


class _Boom(ContextProvider):
    name = "boom"
    cadence = "static"

    def render(self, state):
        raise RuntimeError("provider blew up")


# ---- assembler ----------------------------------------------------------------

def test_static_cached_per_turn_rerendered():
    s, p = _Static("STATIC"), _PerTurn("VOLATILE")
    a = ContextAssembler([s, p])
    a.assemble({})
    a.assemble({})
    assert s.calls == 1   # static rendered once, then cached
    assert p.calls == 2   # per_turn rendered every turn


def test_static_precedes_per_turn_regardless_of_order():
    # per_turn has a LOWER order than static, but must still land in the suffix
    s = _Static("STATIC")
    p = _PerTurn("VOLATILE")
    p.order = 1
    out = ContextAssembler([s, p]).assemble({})
    assert out.index("STATIC") < out.index("VOLATILE")


def test_finalize_appends_instruction():
    out = ContextAssembler([_Static("X")]).assemble({}, finalize=True)
    assert out.startswith("X")
    assert "final answer" in out.lower()


def test_provider_error_is_swallowed():
    out = ContextAssembler([_Static("OK"), _Boom()]).assemble({})
    assert out == "OK"  # boom omitted, turn survives


def test_disabled_provider_excluded():
    s = _Static("OK")
    d = _Static("NOPE")
    d.name = "d"
    d.enabled = False
    out = ContextAssembler([s, d]).assemble({})
    assert "NOPE" not in out


def test_per_section_budget_clips():
    big = _Static("x" * 1000)
    big.budget_tokens = 10  # ~40 chars
    out = ContextAssembler([big]).assemble({})
    assert "truncated" in out
    assert len(out) < 200


# ---- helpers ------------------------------------------------------------------

def test_clip_noop_under_budget():
    assert clip_to_tokens("hello", 100) == "hello"
    assert clip_to_tokens("hello", 0) == "hello"  # no budget = no clip


def test_estimate_tokens_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_rounds_this_turn_counts_ai_since_human():
    from langchain_core.messages import AIMessage, HumanMessage

    msgs = [HumanMessage(content="a"), AIMessage(content="1"),
            AIMessage(content="2"), HumanMessage(content="b"), AIMessage(content="3")]
    assert rounds_this_turn(msgs) == 1  # only the AIMessage after the last human


# ---- config -------------------------------------------------------------------

def test_apply_to_providers_overrides_and_ignores_bad_types():
    p = _Static("X")
    apply_to_providers([p], {"providers": {"s": {"enabled": False, "order": 99,
                                                  "budget_tokens": "oops"}}})
    assert p.enabled is False
    assert p.order == 99
    assert p.budget_tokens == p.default_budget_tokens  # bad type ignored


def test_global_budget_default_and_override():
    assert global_budget({}) == 8000
    assert global_budget({"budget_tokens": 1234}) == 1234
    assert global_budget({"budget_tokens": -5}) == 8000  # invalid → default


# ---- providers ----------------------------------------------------------------

def test_base_prompt_provider():
    assert BasePromptProvider("hi").render({}) == "hi"
    assert BasePromptProvider("").render({}) is None


def test_datetime_is_per_turn():
    assert DateTimeProvider().cadence == "per_turn"
    assert "date/time" in DateTimeProvider().render({}).lower()


def test_project_instructions_discovers_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# rules\nbe terse")
    (tmp_path / ".git").mkdir()
    out = ProjectInstructionsProvider(str(tmp_path)).render({})
    assert "be terse" in out
    assert "Project instructions" in out


def test_project_instructions_none_when_absent(tmp_path):
    (tmp_path / ".git").mkdir()
    assert ProjectInstructionsProvider(str(tmp_path)).render({}) is None


def test_build_assembler_smoke():
    a = build_assembler("SYS", os.getcwd())
    out = a.assemble({"messages": []})
    assert out.startswith("SYS")
