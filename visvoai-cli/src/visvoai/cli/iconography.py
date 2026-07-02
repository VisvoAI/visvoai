"""One icon vocabulary for the whole TUI.

Every widget/screen imports its glyphs from here instead of improvising, so the
same concept always looks the same everywhere (and a glyph change is one edit).
Paired with a theme token name where the icon has a canonical accent — pass that
key to `theme.palette(widget)` at render time (never hardcode colors).

Vocabulary (keep this table small — icons earn a slot by being reused):

  Row markers
    POINTER      ❯   the active/selected row (all pickers)
  States (things that can be on/off/broken)
    STATE_OK     ●   connected / healthy / on          → success
    STATE_RUN    ⏵   actively running (a process)      → success
    STATE_FAIL   ✗   failed / errored                  → error
    STATE_ATTN   !   needs the user (approval, action) → warning
    STATE_OFF    ·   disabled by config                → muted
    STATE_IDLE   ○   finished / inactive (was alive)   → muted
  Domain
    GIT          ⎇   git branch
    MODE_CHIP    ◆   HITL mode chip (reserved: mode ONLY — do not reuse)
"""

POINTER = "❯"

STATE_OK = "●"
STATE_RUN = "⏵"
STATE_FAIL = "✗"
STATE_ATTN = "!"
STATE_OFF = "·"
STATE_IDLE = "○"

GIT = "⎇"
MODE_CHIP = "◆"

# State → (icon, theme token) for the common lifecycle vocabulary. Screens map
# their domain states onto these; the token is a `theme.palette()` key.
STATE_STYLE: dict[str, tuple[str, str]] = {
    "ok":       (STATE_OK, "success"),
    "running":  (STATE_RUN, "success"),
    "failed":   (STATE_FAIL, "error"),
    "attention": (STATE_ATTN, "warning"),
    "disabled": (STATE_OFF, "muted"),
    "idle":     (STATE_IDLE, "muted"),
}
