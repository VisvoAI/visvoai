"""visvoai TUI themes — built from the shared brand tokens.

`palette_tokens.json` (vendored next to this module) holds the brand palette; this
module turns those tokens into Textual `Theme` objects. The JSON is generated from
the brand's design tokens by a build-time script kept in the platform — the CLI
ships the generated output, not the generator.

Each palette (default/cosmic/sunset/emerald/warm/technical) becomes two Textual
themes — `visvo-<palette>-light` and `visvo-<palette>-dark`. Widget CSS
uses native Textual variables ($primary, $surface, $secondary, …) plus a few
custom ones ($muted, $hover, $diff-add-bg, …). Rich `render()` code reads the
live values via `palette(widget)` so a theme switch is reflected on re-render.
"""
from __future__ import annotations

import json
from pathlib import Path

from textual.theme import Theme

_TOKENS = json.loads((Path(__file__).parent / "palette_tokens.json").read_text())["palettes"]

# Human labels (mirror the GUI's appearance settings).
PALETTE_LABELS: dict[str, str] = {
    "default": "Default Slate",
    "cosmic": "Cosmic Aurora",
    "sunset": "Sunset Horizon",
    "emerald": "Emerald Helix",
    "warm": "Warm & Human",
    "technical": "Technical Utilitarian",
}
PALETTES = list(PALETTE_LABELS)

# Mode-level colors the GUI doesn't vary per palette: success/warning, plus the
# CLI-only terminal surface tints for diffs and error blocks.
_MODE = {
    "light": {
        "success": "#059669", "warning": "#b45309",
        "diff-add-bg": "#dcfce7", "diff-del-bg": "#fee2e2", "error-bg": "#fef2f2",
    },
    "dark": {
        "success": "#34d399", "warning": "#fbbf24",
        "diff-add-bg": "#0f2a1c", "diff-del-bg": "#2a1015", "error-bg": "#1f1015",
    },
}

DEFAULT_PALETTE = "cosmic"           # GUI's "recommended for Visvo" palette
DEFAULT_THEME = "visvo-cosmic-dark"  # used only when the terminal can't be probed


def theme_name(palette: str, mode: str) -> str:
    return f"visvo-{palette}-{mode}"


def parse_theme(name: str) -> tuple[str, str]:
    """'visvo-cosmic-dark' -> ('cosmic', 'dark')."""
    _, palette, mode = name.split("-", 2)
    return palette, mode


def _luminance(hex_color: str) -> float:
    """Perceived luminance (0–1) of a '#rrggbb' color (Rec. 601 weights)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def mode_for_bg(term_bg: str | None) -> str:
    """'light' or 'dark' from the terminal background luminance — so text colours
    suit the actual terminal. Unknown/unprobeable → 'dark' (the historical default)."""
    if not term_bg:
        return "dark"
    try:
        return "light" if _luminance(term_bg) > 0.5 else "dark"
    except (ValueError, IndexError):
        return "dark"


def default_theme_for_bg(term_bg: str | None) -> str:
    """The startup theme: the default palette in the light/dark mode that matches
    the terminal's background."""
    return theme_name(DEFAULT_PALETTE, mode_for_bg(term_bg))


def _build(palette: str, mode: str) -> Theme:
    t = _TOKENS[palette][mode]
    m = _MODE[mode]
    # The GUI's light `muted` (#a1a1aa) is tuned for grey card surfaces; on a plain
    # white terminal it's too pale (washed). Darken it to a readable medium grey so
    # muted text (tool targets, rails, reasoning) keeps contrast in light mode.
    muted = "#52525b" if mode == "light" else t["muted"]
    return Theme(
        name=theme_name(palette, mode),
        dark=(mode == "dark"),
        primary=t["accent"],       # the colorful brand accent drives the CLI
        secondary=t["secondary"],
        accent=t["accent"],
        # Pure white for primary text on dark themes (more prominent / easier to
        # read than the GUI's off-white); light themes keep their dark foreground.
        foreground="#ffffff" if mode == "dark" else t["foreground"],
        background=t["background"],
        surface=t["surface"],
        panel=t["panel"],
        success=m["success"],
        warning=m["warning"],
        error=t["error"],
        variables={
            "muted": muted,
            "hover": t["hover"],
            "diff-add-bg": m["diff-add-bg"],
            "diff-del-bg": m["diff-del-bg"],
            "error-bg": m["error-bg"],
        },
    )


THEMES: list[Theme] = [_build(p, mode) for p in PALETTES for mode in ("light", "dark")]


def palette(widget) -> dict:
    """Live theme colors (concrete hexes) for use inside Rich render() code."""
    return widget.app.theme_variables
