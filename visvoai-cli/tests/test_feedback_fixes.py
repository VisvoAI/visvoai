"""User-feedback tests (round 2) — verify the revised fixes:

1. Note input: Tab on an option enters EDIT MODE for that OptionRow (the label is
   replaced by an Input inside the OptionRow). Enter saves, Esc cancels.
2. Quit confirm: subtle footer hint with 2s timer, no escape option.
3. Diff cleanup: when the Selection is removed, the previous CleanDiff loses its
   'followed' class so its bottom border is restored.
"""
from __future__ import annotations

import asyncio

import pytest

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import CleanDiff, Selection
from visvoai.cli.widgets.selection import OptionRow


async def _mount_selection(app, prompt: str, options: list[str], recommended: int = 0):
    return await app.ask_choice(prompt, options, recommended=recommended)


# ── Fix #1: Tab → OptionRow enters edit mode ────────────────────────────────


@pytest.mark.asyncio
async def test_tab_on_active_option_enters_edit_mode():
    """Tab on the active option enters edit mode for THAT OptionRow."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B", "C"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        assert len(rows) == 3

        # Initially no row in edit mode
        for row in rows:
            assert not row.is_editing()

        # Press Tab — active row (idx 0) enters inline edit mode and takes focus
        await pilot.press("tab")
        await pilot.pause()

        assert rows[0].is_editing()
        assert rows[0].has_focus
        # Other rows still in display mode
        for row in rows[1:]:
            assert not row.is_editing()

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_edit_mode_renders_label_and_inline_hint():
    """In edit mode the row still shows its label (inline), plus a note hint."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["Apply the edit", "Skip"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        rows = list(sel.query(OptionRow))
        rendered = str(rows[0].render())
        assert "Apply the edit" in rendered      # label stays visible inline
        assert "enter saves" in rendered          # inline hint shown when empty

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_tab_edits_currently_active_option_not_always_first():
    """After navigating to option 1 with ↓, Tab edits option 1 (not 0)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B", "C"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert sel.idx == 1

        await pilot.press("tab")
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        assert rows[1].is_editing()
        assert not rows[0].is_editing()
        assert not rows[2].is_editing()

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_enter_in_edit_mode_saves_note_to_option_row():
    """Typing a note + Enter in edit mode saves the note to the OptionRow and exits edit mode."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        await pilot.press("tab")
        await pilot.pause()
        assert rows[0].has_focus

        for ch in "my note":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Edit mode exited
        assert not rows[0].is_editing()
        # Note saved on the OptionRow
        assert rows[0].note == "my note"
        # Selection has focus again
        assert sel.has_focus

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_esc_in_edit_mode_cancels_without_saving():
    """Esc in edit mode exits without saving the note."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        await pilot.press("tab")
        await pilot.pause()
        for ch in "discard me":
            await pilot.press(ch)
        await pilot.press("escape")
        await pilot.pause()

        assert not rows[0].is_editing()
        assert rows[0].note == ""

        sel._resolve((0, ""))
        await task


@pytest.mark.asyncio
async def test_selecting_option_with_note_returns_note():
    """Selecting an option that has a saved note resolves with that note."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        # Tab into edit mode, type note, Enter to save
        await pilot.press("tab")
        for ch in "my note":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        # Now Enter again to select the option
        await pilot.press("enter")
        await pilot.pause()

        idx, note = await task
        assert idx == 0
        assert note == "my note"


@pytest.mark.asyncio
async def test_saved_note_visible_as_suffix_in_display_mode():
    """After saving, the note shows as a suffix on the option label."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(_mount_selection(
            app, "Choose:", ["A", "B"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)
        sel.focus()
        await pilot.pause()

        rows = list(sel.query(OptionRow))
        await pilot.press("tab")
        for ch in "tag me":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

        from rich.console import Console
        import io
        buf = io.StringIO()
        Console(file=buf, force_terminal=False, width=120).print(rows[0].render())
        text = buf.getvalue()
        assert "tag me" in text
        assert "A" in text  # original label still present

        sel._resolve((0, ""))
        await task


# ── Fix #2: Quit — footer hint + 2s timer, no escape ────────────────────────


@pytest.mark.asyncio
async def test_quit_first_ctrlq_replaces_input_with_hint():
    """First Ctrl+Q replaces the input prompt with a quit hint (no bordered section)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        bottom = app.screen.query_one("#bottom", Vertical)
        # Prompt row hidden (kept in DOM to preserve history), hint Static present
        assert bottom.query_one("#prompt-row").display is False
        hint = bottom.query_one("#quit-hint", Static)
        assert hint is not None
        assert app._quitting is True


@pytest.mark.asyncio
async def test_quit_timer_reverts_after_2_seconds():
    """Without a second Ctrl+Q within 2s, the hint reverts to the input prompt."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app._quitting is True

        # Pilot.pause(seconds) advances simulated time
        await pilot.pause(2.5)
        await pilot.pause()

        assert app._quitting is False
        bottom = app.screen.query_one("#bottom", Vertical)
        assert bottom.query_one("#prompt-row").display is True


@pytest.mark.asyncio
async def test_quit_esc_does_not_cancel():
    """Esc does NOT cancel the quit state — only the 2s timer does."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app._quitting is True

        await pilot.press("escape")
        await pilot.pause()
        # Still in quit state — Esc had no effect
        assert app._quitting is True


@pytest.mark.asyncio
async def test_quit_second_ctrlq_within_window_exits(monkeypatch):
    """Second Ctrl+Q within the 2s window calls app.exit()."""
    app = VisvoApp()
    exits = []
    monkeypatch.setattr(app, "exit", lambda *a, **kw: exits.append(True))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert exits == []
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert exits == [True]


# ── Selection teardown ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_selection_resolves_and_removes_cleanly():
    """Resolving a Selection removes it without error (borderless; no attach logic)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.screen.query_one("#log", VerticalScroll)
        await log.mount(CleanDiff("test.toml", [("add", "x = 1")]))
        await pilot.pause()

        task = asyncio.create_task(_mount_selection(
            app, "Apply?", ["Yes", "No"], recommended=0
        ))
        await pilot.pause()
        sel = app.screen.query_one(Selection)

        sel._resolve((0, ""))
        await task
        await pilot.pause()
        assert not app.screen.query(Selection)        # removed
        assert len(log.query(CleanDiff)) == 1          # diff untouched