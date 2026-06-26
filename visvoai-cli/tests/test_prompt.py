"""PromptArea tests — submit, multi-line, paste, and history recall."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets.prompt import PromptArea


@pytest.mark.asyncio
async def test_enter_submits_and_clears():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        for ch in "hello":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert p.text == ""
        assert p._history == ["hello"]


@pytest.mark.asyncio
async def test_empty_enter_does_not_submit():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        # empty prompt
        await pilot.press("enter")
        await pilot.pause()
        assert p._history == []
        # whitespace-only prompt
        for ch in ("space", "space"):
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert p._history == []      # still nothing submitted
        assert p.text.strip() == ""  # whitespace left as-is, not sent


@pytest.mark.asyncio
async def test_ctrl_j_inserts_newline_without_submitting():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        for ch in "ab":
            await pilot.press(ch)
        await pilot.press("ctrl+j")
        for ch in "cd":
            await pilot.press(ch)
        await pilot.pause()
        assert p.text == "ab\ncd"
        assert p._history == []  # not submitted


@pytest.mark.asyncio
async def test_alt_enter_inserts_newline_without_submitting():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        for ch in "ab":
            await pilot.press(ch)
        await pilot.press("alt+enter")
        for ch in "cd":
            await pilot.press(ch)
        await pilot.pause()
        assert p.text == "ab\ncd"
        assert p._history == []  # not submitted


@pytest.mark.asyncio
async def test_pasted_multiline_text_preserved():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        p.insert("first line\nsecond line")
        await pilot.pause()
        assert p.text == "first line\nsecond line"


@pytest.mark.asyncio
async def test_large_paste_collapses_to_pill_and_expands_on_submit():
    """A big paste shows a compact marker in the buffer, but the full text is what
    gets submitted (and recalled)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        big = "\n".join(f"line {i}" for i in range(40))   # 40 lines ≥ threshold

        class _E:   # minimal stand-in for a textual Paste event
            text = big
            def prevent_default(self): pass
            def stop(self): pass
        p.on_paste(_E())
        await pilot.pause()
        # buffer shows the pill, not the wall of text
        assert p.text == "[Pasted #1 · 40 lines]"
        # submit expands it back to the full content
        p._submit()
        await pilot.pause()
        assert p._history and p._history[-1] == big
        assert p.text == ""               # cleared
        assert p._pastes == {}            # map reset after submit


@pytest.mark.asyncio
async def test_small_paste_inserts_inline():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        # A short paste (< threshold) is not collapsed → no pill recorded.
        class _E:
            text = "a\nb\nc"
            def prevent_default(self): pass
            def stop(self): pass
        p.on_paste(_E())
        await pilot.pause()
        assert p._pastes == {}            # nothing collapsed


@pytest.mark.asyncio
async def test_up_recalls_previous_prompt():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        for word in ("one", "two"):
            for ch in word:
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()
        # Up once → most recent ("two"); up again → "one"
        await pilot.press("up")
        await pilot.pause()
        assert p.text == "two"
        await pilot.press("up")
        await pilot.pause()
        assert p.text == "one"


@pytest.mark.asyncio
async def test_down_restores_draft_after_history_nav():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        for ch in "saved":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        # Type a draft, recall history, then come back down to the draft
        for ch in "draft":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert p.text == "saved"
        await pilot.press("down")
        await pilot.pause()
        assert p.text == "draft"
