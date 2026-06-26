"""CleanDiff syntax highlighting — changed lines are tokenized per language."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.mock import DIFF_CHANGES
from visvoai.cli.widgets import CleanDiff
from visvoai.cli.widgets.diff import DiffLine


async def _mount(app, pilot, filename: str) -> CleanDiff:
    cd = CleanDiff(filename, DIFF_CHANGES)
    await app.query_one("#log").mount(cd)
    await pilot.pause()
    return cd


@pytest.mark.asyncio
async def test_known_language_highlights_code():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        cd = await _mount(app, pilot, "config.toml")
        syn = cd._highlighter()
        assert syn is not None
        t = cd._code(syn, 'api_key_env = "ANTHROPIC_API_KEY"', "white")
        assert len(t.spans) > 1               # tokenized into several styled spans
        assert not t.plain.endswith("\n")     # trailing newline stripped


@pytest.mark.asyncio
async def test_unknown_language_falls_back_flat():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        cd = await _mount(app, pilot, "notes.zzzunknown")
        assert cd._highlighter() is None
        t = cd._code(None, "some plain text", "white")
        assert len(t.spans) <= 1              # no tokenization, single flat style


@pytest.mark.asyncio
async def test_rows_built_and_survive_theme_switch():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        cd = await _mount(app, pilot, "config.toml")
        assert len(cd.query(DiffLine)) == len(DIFF_CHANGES)
        app.action_toggle_mode()              # triggers restyle → light syntax theme
        await pilot.pause()
        assert len(cd.query(DiffLine)) == len(DIFF_CHANGES)
        assert cd._highlighter() is not None


# ── side-by-side layout (Style B) ────────────────────────────────────────────
import pytest as _pytest
from visvoai.cli import VisvoApp as _VisvoApp
from visvoai.cli.widgets import CleanDiff as _CleanDiff
from visvoai.cli.widgets.diff import DiffLine as _DiffLine

_SIDE_CHANGES = [
    ("ctx", "def f(x):"),
    ("del", "    return x + 1"),
    ("add", "    return x + 2"),
    ("ctx", "    done"),
]


@_pytest.mark.asyncio
async def test_unified_when_explicit():
    app = _VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        d = _CleanDiff("f.py", _SIDE_CHANGES, diff_layout="unified")
        await app.query_one("#log").mount(d)
        await pilot.pause()
        assert d._built_layout == "unified"
        # unified rows carry no center divider
        assert not any("│" in str(r.render()) for r in d.query(_DiffLine))


@_pytest.mark.asyncio
async def test_side_by_side_when_explicit_and_wide():
    app = _VisvoApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        d = _CleanDiff("f.py", _SIDE_CHANGES, diff_layout="side")
        await app.query_one("#log").mount(d)
        await pilot.pause()
        assert d._built_layout == "side"
        # the before/after divider appears in rows
        assert any("│" in str(r.render()) for r in d.query(_DiffLine))


@_pytest.mark.asyncio
async def test_side_falls_back_to_unified_when_narrow():
    app = _VisvoApp()
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()
        d = _CleanDiff("f.py", _SIDE_CHANGES, diff_layout="side")
        await app.query_one("#log").mount(d)
        await pilot.pause()
        # 60 cols < SIDE_BY_SIDE_MIN_WIDTH → unified even though "side" requested
        assert d._built_layout == "unified"
