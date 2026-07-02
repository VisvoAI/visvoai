"""Plan A foundations: icon vocabulary, shared screen chrome, token-only colors."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from visvoai.cli import iconography as ic
from visvoai.cli.screens.chrome import CHROME_CSS, hint

SCREENS = Path(__file__).parent.parent / "src" / "visvoai" / "cli" / "screens"


def test_state_style_covers_lifecycle_and_uses_theme_tokens():
    assert set(ic.STATE_STYLE) == {"ok", "running", "failed", "attention",
                                   "disabled", "idle"}
    for icon, token in ic.STATE_STYLE.values():
        assert icon and token in {"success", "error", "warning", "muted"}


def test_mode_chip_reserved():
    # ◆ is the HITL mode chip only — no state maps to it.
    assert all(icon != ic.MODE_CHIP for icon, _ in ic.STATE_STYLE.values())


def test_hint_format():
    assert hint(("enter", "select"), ("esc", "close")) == \
        "[b]enter[/] select   ·   [b]esc[/] close"


def test_chrome_css_has_the_shared_classes():
    for cls in (".sc-box", ".sc-title", ".sc-sub", ".sc-list", ".sc-hint", ".sc-empty"):
        assert cls in CHROME_CSS


@pytest.mark.parametrize("fname", ["mcp_view.py", "process_view.py"])
def test_reference_screens_use_no_literal_rich_colors(fname):
    """The convention: colors only via theme tokens. Guard the two reference
    adopters against style="green"/"red"/"yellow" literals creeping back."""
    src = (SCREENS / fname).read_text()
    assert not re.search(r'style="(green|red|yellow|blue|magenta|cyan)"', src), fname


# ── Plan B: all screens on the shared chrome ─────────────────────────────────

@pytest.mark.parametrize("fname", ["mcp_view.py", "process_view.py", "rewind_view.py",
                                   "branch_view.py", "sessions.py", "model_view.py"])
def test_screens_use_shared_chrome(fname):
    src = (SCREENS / fname).read_text()
    assert "CHROME_CSS" in src, f"{fname} not on shared chrome"
    assert "hint(" in src, f"{fname} not using shared hint()"


def test_no_screen_hand_rolls_title_css():
    """The drifting per-screen `#x-title {…}` rules are gone — title styling
    comes only from .sc-title in chrome.py."""
    for f in SCREENS.glob("*_view.py"):
        src = f.read_text()
        assert not re.search(r"#\w+-title \{", src), f.name
    assert not re.search(r"#sessions-title \{", (SCREENS / "sessions.py").read_text())


# ── Plan C: stream widgets stay on the vocabulary ────────────────────────────

WIDGETS = SCREENS.parent / "widgets"


def test_no_literal_rich_colors_in_stream_widgets():
    """Stream widgets take colors only from theme tokens (dim/bold modifiers ok)."""
    for f in WIDGETS.glob("*.py"):
        src = f.read_text()
        assert not re.search(r'style="(green|red|yellow|blue|magenta|cyan)"', src), f.name


def test_note_kinds_live_in_iconography():
    from visvoai.cli.iconography import GIT, MILESTONE, NOTE_KINDS
    from visvoai.cli.widgets.system_note import _KINDS
    assert _KINDS is NOTE_KINDS                       # one table, imported
    assert NOTE_KINDS["branch"][0] == MILESTONE       # conversation branch = ◈
    assert all(icon != GIT for icon, _ in NOTE_KINDS.values())  # ⎇ stays git-only
