"""GitScreen — full-screen commit view + interactive staging + commit flow.

UI behavior is driven with a mock status dict (cwd=None → mock mode, no real git).
The real commit→note wiring is covered by monkeypatching `gitio`.
"""
from __future__ import annotations

import pytest
from textual.widgets import Input

from visvoai.cli import VisvoApp, gitio
from visvoai.cli.mock import GIT_STATUS
from visvoai.cli.screens import GitScreen
from visvoai.cli.screens.git_view import CommitMessageArea, GitFileRow
from visvoai.cli.widgets import SystemNote


async def _push_git(app, pilot, status=None) -> GitScreen:
    """Push the git screen directly with a mock status (cwd=None → mock mode)."""
    app.push_screen(GitScreen(status or GIT_STATUS))
    for _ in range(40):
        await pilot.pause()
        if isinstance(app.screen, GitScreen):
            return app.screen
    raise AssertionError("git screen never opened")


def _status(files, branch="agent/x", message="msg") -> dict:
    return {"branch": branch, "suggested_message": message, "files": files}


@pytest.mark.asyncio
async def test_git_view_lists_files_and_prefills_message():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_git(app, pilot)
        assert len(screen.query(GitFileRow)) == len(GIT_STATUS["files"])
        subject = screen.query_one("#git-subject", Input)
        assert subject.value == GIT_STATUS["suggested_message"]  # summary prefilled
        assert screen.query_one(CommitMessageArea).text == ""    # description starts empty


@pytest.mark.asyncio
async def test_esc_cancels_without_committing():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _push_git(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, GitScreen)
        assert not app.query(SystemNote)    # nothing committed → no marker


@pytest.mark.asyncio
async def test_toggle_stage_flips_file(monkeypatch):
    """ctrl+s on the current file flips its staged state (mock mode)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        status = _status([
            {"path": "a.py", "state": "M", "staged": True, "adds": 1, "dels": 0},
            {"path": "b.py", "state": "M", "staged": False, "adds": 2, "dels": 0},
        ])
        screen = await _push_git(app, pilot, status)
        # current = first row (staged a.py)
        assert screen._files_flat[0]["path"] == "a.py" and screen._files_flat[0]["staged"]
        await screen.select_file(0)   # staging acts on the file under review
        await pilot.pause()
        await screen.action_toggle_stage()
        await pilot.pause()
        a = next(f for f in screen.status["files"] if f["path"] == "a.py")
        assert a["staged"] is False   # unstaged after toggle


@pytest.mark.asyncio
async def test_commit_requires_staged_files():
    """Commit with nothing staged keeps the screen open (no empty commit)."""
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        status = _status([
            {"path": "a.py", "state": "M", "staged": False, "adds": 1, "dels": 0},
        ])
        screen = await _push_git(app, pilot, status)
        screen.query_one("#git-subject", Input).value = "a summary"  # subject set; nothing staged
        await screen._commit()
        await pilot.pause()
        assert isinstance(app.screen, GitScreen)   # stayed open — nothing staged


@pytest.mark.asyncio
async def test_commit_real_flow_renders_note(monkeypatch):
    """action_open_git reads real status + commits via gitio (both monkeypatched);
    sessions then renders the branch note with the real result."""
    fake = {
        "branch": "feature/x", "upstream": "origin/x", "ahead": 1, "behind": 0,
        "suggested_message": "",
        "files": [{"path": "x.py", "state": "M", "staged": True,
                   "adds": 3, "dels": 1, "diff": []}],
    }
    captured = {}

    def _fake_commit(cwd, subject, body=""):
        captured["subject"], captured["body"] = subject, body
        return True, ""

    monkeypatch.setattr(gitio, "working_tree_status", lambda cwd: fake)
    monkeypatch.setattr(gitio, "commit", _fake_commit)

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_git()
        for _ in range(40):
            await pilot.pause()
            if isinstance(app.screen, GitScreen):
                break
        app.screen.query_one("#git-subject", Input).value = "Real commit message"
        app.screen.query_one(CommitMessageArea).text = "A longer description body."
        app.screen.query_one("#git-subject", Input).focus()
        await pilot.pause()
        await pilot.press("enter")          # summary enter → commit
        for _ in range(40):
            await pilot.pause()
            if not isinstance(app.screen, GitScreen):
                break
        assert not isinstance(app.screen, GitScreen)
        # subject + body both reached git as the two -m parts.
        assert captured == {"subject": "Real commit message", "body": "A longer description body."}
        notes = [n for n in app.query(SystemNote) if n.kind == "branch"]
        assert notes and "Real commit message" in notes[0].message
        assert "1 file" in notes[0].message and "feature/x" in notes[0].message


@pytest.mark.asyncio
async def test_open_git_clean_tree_notifies(monkeypatch):
    """No changes (or not a repo) → a notice, no screen pushed."""
    monkeypatch.setattr(gitio, "working_tree_status", lambda cwd: None)
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_git()
        for _ in range(10):
            await pilot.pause()
        assert not isinstance(app.screen, GitScreen)


@pytest.mark.asyncio
async def test_git_review_navigation_and_preview():
    """ctrl+↑/↓ steps through files; the selected row highlights and its diff
    shows in the preview pane (aggregate multi-file review, Case A Turn 7)."""
    from visvoai.cli.widgets import CleanDiff

    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        status = {
            "branch": "agent/print-to-logger",
            "suggested_message": "migrate print() to logger",
            "files": [
                {"path": "utils.py", "state": "M", "staged": True, "adds": 3, "dels": 3,
                 "diff": [("ctx", "def log(x):"), ("del", "    print(x)"), ("add", "    logger.info(x)")]},
                {"path": "routes/items.py", "state": "M", "staged": True, "adds": 1, "dels": 1,
                 "diff": [("del", "print('hi')"), ("add", "logger.info('hi')")]},
                {"path": "README.md", "state": "M", "staged": False, "adds": 1, "dels": 0},
            ],
        }
        screen = await _push_git(app, pilot, status)
        await pilot.pause()

        # Nothing previewed on open — single column, diff panel hidden.
        assert screen._current == -1
        preview = screen.query_one("#git-preview")
        assert len(preview.query(CleanDiff)) == 0
        assert screen.query_one("#git-preview-col").display is False

        # Select the first file → diff panel opens (two columns) + row highlights.
        await screen.select_file(0)
        await pilot.pause()
        assert screen._current == 0
        assert screen.query_one("#git-preview-col").display is True
        rows = sorted(screen.query(GitFileRow), key=lambda r: r.index)
        assert rows[0].has_class("current")
        assert len(preview.query(CleanDiff)) == 1
        assert preview.query_one(CleanDiff).filename == "utils.py"

        # Step to the next file → highlight + preview move with it.
        await screen.action_next_file()
        await pilot.pause()
        assert screen._current == 1
        assert rows[1].has_class("current") and not rows[0].has_class("current")
        assert screen.query_one("#git-preview").query_one(CleanDiff).filename == "routes/items.py"

        # Third file has no diff → graceful placeholder, no crash.
        await screen.action_next_file()
        await pilot.pause()
        assert screen._current == 2
        assert len(screen.query_one("#git-preview").query(CleanDiff)) == 0


@pytest.mark.asyncio
async def test_git_review_clicking_row_selects_it():
    app = VisvoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_git(app, pilot)
        rows = sorted(screen.query(GitFileRow), key=lambda r: r.index)
        if len(rows) > 1:
            rows[1].on_click()
            await pilot.pause()
            assert screen._current == 1
            assert rows[1].has_class("current")
