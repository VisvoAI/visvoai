"""Post-turn contextual nudges (#2) + one-time coachmarks (#3): the decision logic
self-silences as the user learns the relevant features."""
from __future__ import annotations

from visvoai.cli import state
from visvoai.cli.agent_turn import _nudge_text


def test_changed_files_nudge_until_rewind_and_commit_learned():
    assert _nudge_text(3, False, set()) == "3 files changed  ·  /rewind to undo  ·  /commit to keep"
    assert _nudge_text(1, False, set()).startswith("1 file changed")   # singular
    # knowing only one of the two still nudges (they haven't learned the pair)
    assert _nudge_text(2, False, {"rewind"}) is not None
    # both learned → silent
    assert _nudge_text(2, False, {"rewind", "commit"}) is None


def test_failure_nudge_until_rewind_learned():
    assert _nudge_text(0, True, set()) == "that didn't fully work — /rewind goes back to before this turn"
    assert _nudge_text(0, True, {"rewind"}) is None
    # a changed-files turn takes precedence over the failure nudge
    assert _nudge_text(2, True, set()).startswith("2 files changed")


def test_no_nudge_when_nothing_changed_and_no_error():
    assert _nudge_text(0, False, set()) is None


def test_coachmark_flags_are_one_time(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path))
    assert state.mark_shown("coach_checkpoint") is True
    assert state.mark_shown("coach_checkpoint") is False
    assert state.mark_shown("coach_approval") is True     # independent key
    assert state.mark_shown("coach_approval") is False
