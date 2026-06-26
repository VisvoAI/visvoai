"""Theme tests — native Textual themes built from the shared brand tokens."""
from __future__ import annotations

import asyncio

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli import theme
from visvoai.cli.widgets import Selection


def test_themes_built_for_all_palettes():
    names = {t.name for t in theme.THEMES}
    assert len(theme.THEMES) == len(theme.PALETTES) * 2
    assert "visvo-cosmic-dark" in names
    assert "visvo-default-light" in names
    assert "visvo-technical-dark" in names


def test_name_parse_roundtrip():
    assert theme.theme_name("warm", "light") == "visvo-warm-light"
    assert theme.parse_theme("visvo-cosmic-dark") == ("cosmic", "dark")


def test_mode_follows_terminal_luminance():
    assert theme.mode_for_bg("#1e1e1e") == "dark"     # dark terminal
    assert theme.mode_for_bg("#fdf6e3") == "light"    # solarized-light bg
    assert theme.mode_for_bg("#ffffff") == "light"
    assert theme.mode_for_bg(None) == "dark"          # unprobeable → historical default
    assert theme.mode_for_bg("garbage") == "dark"     # malformed → safe default
    assert theme.default_theme_for_bg("#ffffff") == "visvo-cosmic-light"
    assert theme.default_theme_for_bg("#000000") == "visvo-cosmic-dark"


@pytest.mark.asyncio
async def test_app_starts_in_terminal_matching_mode():
    # A light terminal → the CLI starts in a light theme (legible dark text), not
    # the hardcoded dark default.
    app = VisvoApp(term_bg="#fdf6e3")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme.endswith("-light")
    dark = VisvoApp(term_bg="#1e1e1e")
    async with dark.run_test() as pilot:
        await pilot.pause()
        assert dark.theme.endswith("-dark")


def test_tokens_match_gui_brand():
    # cosmic dark accent comes straight from the GUI palette
    cosmic = next(t for t in theme.THEMES if t.name == "visvo-cosmic-dark")
    assert cosmic.primary.lower() == "#a78bfa"
    assert cosmic.variables["muted"]  # custom var present


@pytest.mark.asyncio
async def test_app_starts_on_recommended_theme():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == theme.DEFAULT_THEME == "visvo-cosmic-dark"
        # both native and custom variables resolve to concrete colors
        assert app.theme_variables["primary"]
        assert app.theme_variables["muted"]
        assert app.theme_variables["diff-add-bg"]


@pytest.mark.asyncio
async def test_toggle_mode_flips_light_dark_and_reresolves_css():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        before = app.theme_variables["primary"]
        assert theme.parse_theme(app.theme) == ("cosmic", "dark")
        app.action_toggle_mode()
        await pilot.pause()
        assert theme.parse_theme(app.theme) == ("cosmic", "light")
        assert app.theme_variables["primary"] != before  # palette re-resolved


@pytest.mark.asyncio
async def test_background_transparent_when_terminal_unknown():
    """No detected terminal color → transparent base (no forced theme slab)."""
    app = VisvoApp()  # term_bg=None
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.background_colors[0].a == 0   # dark
        app.action_toggle_mode()
        await pilot.pause()
        assert app.screen.background_colors[0].a == 0   # light


@pytest.mark.asyncio
async def test_background_matches_detected_terminal_color():
    """When the terminal bg is detected, the app paints it (seamless blend) and
    keeps it across a theme switch."""
    from textual.color import Color
    app = VisvoApp(term_bg="#1e1e2e")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.background_colors[0] == Color(30, 30, 46)
        app.action_toggle_mode()
        await pilot.pause()
        assert app.screen.background_colors[0] == Color(30, 30, 46)


@pytest.mark.asyncio
async def test_theme_picker_changes_palette_keeps_mode():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        task = asyncio.create_task(app._theme_picker_flow())
        await pilot.pause()
        sel = app.query_one(Selection)
        emerald = theme.PALETTES.index("emerald")
        sel._resolve((emerald, ""))
        await task
        await pilot.pause()
        assert theme.parse_theme(app.theme) == ("emerald", "dark")  # mode preserved
