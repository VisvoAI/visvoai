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
