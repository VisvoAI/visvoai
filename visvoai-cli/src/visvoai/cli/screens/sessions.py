"""SessionsScreen — a dedicated full-screen view to resume (or fork) a past
conversation, with live search.

A search box filters the list as you type; ↑/↓ navigate, enter resumes the
highlighted session, esc backs out. `dismiss()` returns the chosen session id (or
None on cancel) to the pushing caller. At integration the mock `SESSIONS` list is
replaced by real threads from `~/.visvoai/projects/<id>/conversations/`.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Static

from visvoai.cli import theme
from visvoai.cli.screens.base import BlendScreen


class SessionRow(Horizontal):
    """One session: title (left, 1fr) + aligned `when · N msgs` metadata (right)."""

    can_focus = False

    DEFAULT_CSS = """
    SessionRow { height: 1; padding: 0 1; }
    SessionRow:hover { background: $hover; }
    SessionRow.active { background: $hover; }
    /* Fixed-width metadata columns so `when` / `msgs` line up across all rows
       regardless of title or value length. Title takes the rest. */
    SessionRow > .sr-title { width: 1fr; text-overflow: ellipsis; }
    SessionRow > .sr-when { width: 12; content-align: right middle; }
    SessionRow > .sr-msgs { width: 10; content-align: right middle; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, session: dict) -> None:
        super().__init__()
        self.index = index
        self.session = session
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="sr-title")
        yield Static(classes="sr-when")
        yield Static(classes="sr-msgs")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def _render_row(self) -> None:
        tv = theme.palette(self)
        s = self.session
        title = Text()
        title.append(" ❯ " if self._active else "   ",
                     style=tv["primary"] if self._active else "dim")
        title.append(s["title"],
                     style=f"bold {tv['primary']}" if self._active else tv["foreground"])
        self.query_one(".sr-title", Static).update(title)
        self.query_one(".sr-when", Static).update(Text(s["when"], style=tv["muted"]))
        self.query_one(".sr-msgs", Static).update(
            Text(f"{s['msgs']} msgs", style=f"dim {tv['muted']}")
        )

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class SessionsScreen(BlendScreen):
    """Full-screen, searchable session picker. `dismiss(id | None)`."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = """
    SessionsScreen > #sessions-box { padding: 1 2; height: 1fr; }
    #sessions-title { text-style: bold; color: $primary; padding: 0 1; }
    #sessions-search, #sessions-search:focus {
        border: none; background: transparent; padding: 0 1; margin: 0 0 1 0;
        border-bottom: solid $primary;
    }
    #sessions-list { height: 1fr; }
    #sessions-hint { color: $muted; padding: 0 1; margin: 1 0 0 0; }
    #sessions-empty { color: $muted; padding: 0 1; }
    """

    def __init__(self, sessions: list[dict]) -> None:
        super().__init__()
        self.sessions = sessions
        self.filtered = list(sessions)
        self.idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="sessions-box"):
            yield Static("Resume a conversation", id="sessions-title")
            yield Input(placeholder="search sessions…", id="sessions-search")
            with VerticalScroll(id="sessions-list"):
                for i, s in enumerate(self.filtered):
                    yield SessionRow(i, s)
            yield Static("↑/↓ navigate   enter resume   esc close", id="sessions-hint")

    def on_mount(self) -> None:
        super().on_mount()  # blend with the terminal background
        self.query_one("#sessions-search", Input).focus()
        self._sync()

    def _rows(self) -> list[SessionRow]:
        return list(self.query(SessionRow))

    def _sync(self) -> None:
        for i, row in enumerate(self._rows()):
            row.set_active(i == self.idx)

    async def on_input_changed(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        self.filtered = [s for s in self.sessions if q in s["title"].lower()]
        self.idx = 0
        lst = self.query_one("#sessions-list", VerticalScroll)
        await lst.remove_children()
        if self.filtered:
            await lst.mount_all(SessionRow(i, s) for i, s in enumerate(self.filtered))
            self._sync()
        else:
            await lst.mount(Static("no matching sessions", id="sessions-empty"))

    def on_key(self, event) -> None:
        if not self.filtered:
            return
        if event.key == "up":
            self.idx = (self.idx - 1) % len(self.filtered); self._sync(); event.stop()
        elif event.key == "down":
            self.idx = (self.idx + 1) % len(self.filtered); self._sync(); event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._resume()

    def on_session_row_chosen(self, msg: SessionRow.Chosen) -> None:
        self.idx = msg.index
        self._resume()

    def _resume(self) -> None:
        self.dismiss(self.filtered[self.idx]["id"] if self.filtered else None)

    def action_close(self) -> None:
        self.dismiss(None)
