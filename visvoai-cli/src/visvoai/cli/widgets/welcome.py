"""Launch chrome: the Welcome card and the two-column WelcomeBanner.

Distinct from the conversation-stream widgets — this is the idle/launch screen.
Both take markup *factories* (not baked strings) so their theme-colored content
rebuilds on a palette switch via restyle()."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class Welcome(Static):
    """Intro / info card. Takes a markup *factory* (not a baked string) so its
    theme-colored content can be rebuilt on a palette switch via restyle()."""

    DEFAULT_CSS = """
    Welcome {
        background: transparent;
        border-bottom: solid $primary-darken-2;
        padding: 0 1 1 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, markup_factory) -> None:
        super().__init__()
        self._factory = markup_factory

    def on_mount(self) -> None:
        self.update(self._factory())

    def restyle(self) -> None:
        self.update(self._factory())


class WelcomeBanner(Horizontal):
    """Two-column launch banner: a left brand column (name + tagline) and a wider
    right column (70%) for the rest. Both take markup factories so they re-theme."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        background: transparent;
        border-bottom: solid $primary-darken-2;
        padding: 0 1 1 1;
        margin: 0 0 1 0;
    }
    WelcomeBanner > #wb-left { width: auto; height: auto; padding: 0 2 0 1; }
    WelcomeBanner > #wb-right {
        width: 1fr;
        height: auto;
        padding: 0 1 0 2;
        border-left: solid $primary-darken-2;
    }
    """

    def __init__(self, left_factory, right_factory) -> None:
        super().__init__()
        self._left = left_factory
        self._right = right_factory

    def compose(self) -> ComposeResult:
        yield Static(id="wb-left")
        yield Static(id="wb-right")

    def on_mount(self) -> None:
        self.restyle()

    def restyle(self) -> None:
        self.query_one("#wb-left", Static).update(self._left())
        self.query_one("#wb-right", Static).update(self._right())
