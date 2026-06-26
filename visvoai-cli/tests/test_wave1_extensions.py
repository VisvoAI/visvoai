"""Wave-1 small extensions: SystemNote stale kind, StatusBar mode chip,
Selection compact mode, PromptArea large-paste signal."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.widgets import Selection, StatusBar, SystemNote
from visvoai.cli.widgets.prompt import PromptArea
from visvoai.cli.widgets.selection import OptionRow


@pytest.mark.asyncio
async def test_system_note_stale_kind():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        n = SystemNote("items.py changed since read — re-reading", kind="stale")
        await app.query_one("#log").mount(n)
        await pilot.pause()
        assert "↺" in str(n.render())
        assert "re-reading" in str(n.render())


@pytest.mark.asyncio
async def test_statusbar_mode_chip():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        sb = StatusBar(model="gemini", location="repo:main")
        await app.query_one("#log").mount(sb)
        await pilot.pause()
        left = app.query_one("#log").query_one("#sb-left")
        sb.set_mode("plan")
        assert "plan" in str(left.render())
        sb.set_mode(None)
        assert "plan" not in str(left.render())


@pytest.mark.asyncio
async def test_selection_compact_drops_hint():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        full = Selection("Apply?", ["yes", "no"])
        await app.query_one("#log").mount(full)
        await pilot.pause()
        assert len(full.query(".sel-hint")) == 1

        compact = Selection("Apply guard?", ["yes", "no"], compact=True)
        await app.query_one("#log").mount(compact)
        await pilot.pause()
        assert len(compact.query(".sel-hint")) == 0
        # options still present and selectable
        assert len(compact.query(OptionRow)) == 2


def test_prompt_large_paste_signal():
    """on_paste collapses a large paste to a pill (records it + signals); a small
    paste falls through to the default inline insert."""
    p = PromptArea()
    posted: list = []
    p.post_message = lambda m: posted.append(m)  # type: ignore[assignment]

    class _E:   # minimal Paste event: text + the two methods on_paste calls
        def __init__(self, text): self.text = text
        def prevent_default(self): pass
        def stop(self): pass

    p.on_paste(_E("\n".join(["x"] * 5)))
    assert not posted
    assert p._pastes == {}            # small paste not collapsed

    big_lines = PromptArea.LARGE_PASTE_LINES
    p.on_paste(_E("\n".join(["x"] * big_lines)))
    # insert(marker) also posts a TextArea.Changed — isolate the LargePaste signal.
    large = [m for m in posted if isinstance(m, PromptArea.LargePaste)]
    assert len(large) == 1 and large[0].lines == big_lines
    assert len(p._pastes) == 1        # collapsed to one pill marker
