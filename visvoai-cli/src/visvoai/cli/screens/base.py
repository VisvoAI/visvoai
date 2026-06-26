"""BlendScreen — a pushed Screen that blends with the terminal background.

The main app paints App+Screen with the detected terminal color so the UI is
seamless (see `VisvoApp._apply_background`). A *pushed* screen gets its own
Screen with the theme's default (opaque) background, which breaks the blend — so
every full-screen view subclasses this to re-apply the same terminal color.
"""
from __future__ import annotations

from textual.screen import Screen


class BlendScreen(Screen):
    def on_mount(self) -> None:
        self.styles.background = getattr(self.app, "_term_bg", None) or "transparent"
