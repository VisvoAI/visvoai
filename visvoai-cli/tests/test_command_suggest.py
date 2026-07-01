"""Did-you-mean command matching (#4) + rotating prompt placeholders (#5)."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp
from visvoai.cli.commands import _closest_command
from visvoai.cli.widgets.prompt import PromptArea


def test_alias_maps_intent_words_to_commands():
    assert _closest_command("undo") == "rewind"
    assert _closest_command("revert") == "rewind"
    assert _closest_command("switch") == "branch"
    assert _closest_command("share") == "export"
    assert _closest_command("exit") == "quit"


def test_fuzzy_matches_typos():
    assert _closest_command("rewnd") == "rewind"
    assert _closest_command("hlep") == "help"
    assert _closest_command("modl") == "model"


def test_no_match_returns_none():
    assert _closest_command("xyzzy") is None
    assert _closest_command("") is None


@pytest.mark.asyncio
async def test_placeholder_rotates(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        first = p.placeholder
        app._rotate_placeholder()
        assert p.placeholder != first
        assert p.placeholder in app._PROMPT_EXAMPLES
