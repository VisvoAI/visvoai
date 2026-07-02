"""Shared chrome for full-screen views: one look for title/sub/list/hint.

Every screen used to hand-roll the same four-part layout with near-identical
but drifting CSS and hint formats. Screens now embed CHROME_CSS (class-based,
so ids stay screen-specific for tests) and build their hint line via hint()
so key help reads identically everywhere.

Usage:
    class FooScreen(BlendScreen):
        DEFAULT_CSS = CHROME_CSS + '''
        FooScreen { align: center top; }
        /* screen-specific rules only */
        '''
        def compose(self):
            with Vertical(classes="sc-box"):
                yield Static("Title …", classes="sc-title")
                yield Static("One-line subtitle.", classes="sc-sub")
                with VerticalScroll(classes="sc-list"):
                    ...
                yield Static(hint(("↑/↓", "navigate"), ("enter", "select"),
                                  ("esc", "close")), classes="sc-hint")
"""
from __future__ import annotations

CHROME_CSS = """
.sc-box { width: 100%; max-width: 120; padding: 1 4; height: 1fr; }
.sc-title { text-style: bold; color: $primary; padding: 0 1; }
.sc-sub { color: $muted; padding: 0 1; margin: 0 0 1 0; }
.sc-list { height: 1fr; }
.sc-hint { color: $muted; padding: 0 1; margin: 1 0 0 0; }
.sc-empty { color: $muted; padding: 0 1; }
"""


def hint(*pairs: tuple[str, str]) -> str:
    """Standard hint line: `[b]key[/] action  ·  [b]key[/] action  ·  …`.
    Keys bold, actions plain, separated by middots — same rhythm on every screen."""
    return "   ·   ".join(f"[b]{key}[/] {action}" for key, action in pairs)
