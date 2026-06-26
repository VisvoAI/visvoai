"""SeverityOutput — error/warning classification + warning-flood fold."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets.output import OutputLine
from visvoai.cli.widgets.severity_output import (
    SeverityOutput,
    WarningFold,
    classify,
)

# A suite run: passing tests, a real failure, and a flood of deprecation warnings.
LINES = [
    "tests/test_orders.py::test_create PASSED",
    "LegacyAPIWarning: Query.get() is deprecated, use Session.get()",
    "tests/test_orders.py::test_list PASSED",
    "MovedIn20Warning: relationship loading changed in 2.0",
    "DeprecationWarning: legacy pattern",
    "tests/test_orders.py::test_get FAILED",
    "E   AssertionError: expected 200",
]


def test_classify():
    assert classify("tests/test_orders.py::test_create PASSED") == "normal"
    assert classify("LegacyAPIWarning: deprecated") == "warning"
    assert classify("E   AssertionError: boom") == "error"
    # error wins when a line could read as both
    assert classify("Error: a deprecated Warning") == "error"


async def _mount(app, pilot, **kw) -> SeverityOutput:
    o = SeverityOutput(LINES, **kw)
    await app.query_one("#log").mount(o)
    await pilot.pause()
    return o


@pytest.mark.asyncio
async def test_folded_hides_warnings_shows_fold():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        o = await _mount(app, pilot)  # folded by default
        fold = o.query_one(WarningFold)
        assert fold.count == 3
        assert "3 warnings" in str(fold.render())
        assert "show" in str(fold.render())
        # 4 non-warning lines render; the 3 warnings are hidden
        assert len(o.query(OutputLine)) == 4


@pytest.mark.asyncio
async def test_toggle_reveals_and_rehides_warnings():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        o = await _mount(app, pilot)
        await o.toggle()
        await pilot.pause()
        # all 7 lines visible now
        assert len(o.query(OutputLine)) == 7
        assert "hide" in str(o.query_one(WarningFold).render())
        await o.toggle()
        await pilot.pause()
        assert len(o.query(OutputLine)) == 4


@pytest.mark.asyncio
async def test_fold_click_toggles():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        o = await _mount(app, pilot)
        o.query_one(WarningFold).on_click()
        await pilot.pause()
        assert len(o.query(OutputLine)) == 7


@pytest.mark.asyncio
async def test_no_warnings_no_fold():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        o = SeverityOutput(["all PASSED", "done"])
        await app.query_one("#log").mount(o)
        await pilot.pause()
        assert len(o.query(WarningFold)) == 0
        assert len(o.query(OutputLine)) == 2
