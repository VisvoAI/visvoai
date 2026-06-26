"""@-mention file picker — open/filter/insert, plus the ranking helper."""
from __future__ import annotations

import pytest

from visvoai.cli import VisvoApp, gitio
from visvoai.cli.widgets.file_menu import FileMenu, FileRow, rank_files
from visvoai.cli.widgets.prompt import PromptArea

_FILES = ["a.py", "src/b.py", "src/c.txt"]


def test_rank_files_basename_first():
    paths = ["src/util/main.py", "main.py", "docs/readme.md", "src/main_helper.py"]
    out = rank_files(paths, "main")
    assert out[0] == "main.py"            # basename match + shortest path wins
    assert "docs/readme.md" not in out    # no substring match → excluded


def test_rank_files_empty_frag_returns_head():
    assert rank_files(_FILES, "") == _FILES


@pytest.mark.asyncio
async def test_at_opens_file_menu(monkeypatch):
    monkeypatch.setattr(gitio, "project_files", lambda cwd, limit=4000: list(_FILES))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        p.text = "@"
        await pilot.pause()
        assert app.query(FileMenu)
        assert p.slash_active is True
        assert len(app.query(FileRow)) == len(_FILES)


@pytest.mark.asyncio
async def test_at_filters_and_enter_inserts(monkeypatch):
    monkeypatch.setattr(gitio, "project_files", lambda cwd, limit=4000: list(_FILES))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        p.text = "@b"
        await pilot.pause()
        assert [r.path for r in app.query(FileRow)] == ["src/b.py"]
        await pilot.press("enter")            # accept → insert mention
        await pilot.pause()
        assert p.text == "@src/b.py "
        assert not app.query(FileMenu)        # menu closed (trailing space ends mention)


@pytest.mark.asyncio
async def test_mention_midtext_with_tab(monkeypatch):
    monkeypatch.setattr(gitio, "project_files", lambda cwd, limit=4000: ["a.py", "src/b.py"])
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        p.text = "explain @a"
        await pilot.pause()
        assert app.query(FileMenu)
        await pilot.press("tab")              # complete → insert, preserving prefix
        await pilot.pause()
        assert p.text == "explain @a.py "


@pytest.mark.asyncio
async def test_no_at_no_menu(monkeypatch):
    monkeypatch.setattr(gitio, "project_files", lambda cwd, limit=4000: list(_FILES))
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        p = app.query_one("#prompt", PromptArea)
        p.focus()
        p.text = "just a question"
        await pilot.pause()
        assert not app.query(FileMenu)
        assert p.slash_active is False
