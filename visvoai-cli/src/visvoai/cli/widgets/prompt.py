"""PromptArea — the multi-line composer at the bottom of the app.

A TextArea that auto-grows with content (up to a cap), submits on Enter, inserts
a literal newline on Ctrl+J / Opt(Alt)+Enter (and Shift+Enter where the terminal
reports it), accepts pasted multi-line text as a block, and recalls submitted
prompts with Up/Down when the caret is at the first/last line.
"""
from __future__ import annotations

from textual.message import Message
from textual.binding import Binding
from textual.widgets import TextArea



class PromptArea(TextArea):
    """Auto-growing prompt composer. Posts `PromptArea.Submitted` on Enter."""

    # Editing parity on top of TextArea's stock set (which already covers
    # ctrl+w/u/k, ctrl+a/e, ctrl+←/→ word jumps, shift-selections, cut/copy/paste):
    # undo/redo, the macOS Option-arrow word motions (terminals send alt+…), and
    # the emacs alt+b/f/d aliases. super+z covers terminals that pass ⌘ through.
    BINDINGS = [
        Binding("ctrl+z,super+z", "undo", "Undo", show=False),
        Binding("ctrl+y,super+shift+z", "redo", "Redo", show=False),
        Binding("alt+left,alt+b", "cursor_word_left", "Word left", show=False),
        Binding("alt+right,alt+f", "cursor_word_right", "Word right", show=False),
        Binding("alt+d", "delete_word_right", "Delete word right", show=False),
    ]

    DEFAULT_CSS = """
    PromptArea, PromptArea:focus {
        height: auto;
        max-height: 10;
        border: none;
        background: transparent;
        padding: 0;
        width: 1fr;
    }
    """

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class SlashKey(Message):
        """A navigation/accept key pressed while the slash menu is open."""

        def __init__(self, action: str) -> None:
            self.action = action  # "up" | "down" | "accept" | "cancel"
            super().__init__()

    class Interrupt(Message):
        """Esc pressed in the prompt — a request to stop an in-flight turn. The app
        decides whether anything is running. (During a HITL the prompt is hidden, so
        esc never reaches here then — it belongs to the Selection/Form instead.)"""

    class LargePaste(Message):
        """A multi-line paste over `LARGE_PASTE_LINES` landed and was collapsed into
        an inline pill marker. The full text is held in `_pastes` and re-expanded at
        submit; this lets the app optionally surface a 'pasted N lines' note."""

        def __init__(self, lines: int) -> None:
            self.lines = lines
            super().__init__()

    # A paste at/above this many lines is "large" enough to collapse into a pill.
    LARGE_PASTE_LINES = 20

    def __init__(self, placeholder: str = "Describe a task, ask a question, or @mention a file…",
                 id: str | None = None) -> None:
        super().__init__(placeholder=placeholder, id=id, soft_wrap=True)
        self._history: list[str] = []
        self._hist_idx: int | None = None
        self._draft: str = ""
        # Large pastes collapse to a marker in the buffer; the real text lives here
        # and is spliced back in at submit. Seq makes each marker unique per paste.
        self._pastes: dict[str, str] = {}
        self._paste_seq = 0
        # Set by the app while a `/` command menu is open. Redirects nav keys to
        # the menu instead of history/submit; typing still flows through to filter.
        self.slash_active = False

    def on_paste(self, event) -> None:
        """Collapse a large paste into a compact inline pill instead of dumping a
        wall of text. Small pastes fall through to the default inline insert."""
        lines = event.text.count("\n") + 1
        if lines < self.LARGE_PASTE_LINES:
            return  # small paste — let the framework insert it inline
        event.prevent_default()
        event.stop()
        self._paste_seq += 1
        marker = f"[Pasted #{self._paste_seq} · {lines} lines]"
        self._pastes[marker] = event.text
        self.insert(marker)
        self.post_message(self.LargePaste(lines))

    def _expand_pastes(self, text: str) -> str:
        """Splice each surviving pill marker back to its full pasted text. A marker
        the user deleted simply isn't present → that paste is dropped (intended)."""
        for marker, full in self._pastes.items():
            text = text.replace(marker, full)
        return text

    async def _on_key(self, event) -> None:
        if self.slash_active and event.key in ("up", "down", "enter", "tab", "escape"):
            event.prevent_default()
            event.stop()
            action = {"enter": "accept", "tab": "complete", "escape": "cancel"}.get(
                event.key, event.key
            )
            self.post_message(self.SlashKey(action))
            return
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.post_message(self.Interrupt())
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self._submit()
            return
        if event.key in ("ctrl+j", "alt+enter", "shift+enter"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        # Delete the previous word — the editor reflex devs expect (macOS
        # option+backspace → alt+backspace; ctrl+w as a common alias).
        if event.key in ("alt+backspace", "ctrl+w"):
            event.prevent_default()
            event.stop()
            self.action_delete_word_left()
            return
        if event.key == "up" and self.cursor_location[0] == 0:
            event.prevent_default()
            event.stop()
            self._history_prev()
            return
        if event.key == "down" and self.cursor_location[0] == self.document.line_count - 1:
            event.prevent_default()
            event.stop()
            self._history_next()
            return
        await super()._on_key(event)

    # ── submit ───────────────────────────────────────────────────────────────
    def _submit(self) -> None:
        value = self._expand_pastes(self.text)
        if not value.strip():
            return  # nothing to send — ignore enter on an empty prompt
        self._history.append(value)
        self._hist_idx = None
        self._draft = ""
        self.text = ""
        self._pastes.clear()
        self.post_message(self.Submitted(value))

    # ── history recall ─────────────────────────────────────────────────────────
    def _history_prev(self) -> None:
        if not self._history:
            return
        if self._hist_idx is None:
            self._draft = self.text
            self._hist_idx = len(self._history) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        self._set_recalled(self._history[self._hist_idx])

    def _history_next(self) -> None:
        if self._hist_idx is None:
            return
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            self._set_recalled(self._history[self._hist_idx])
        else:
            self._hist_idx = None
            self._set_recalled(self._draft)

    def _set_recalled(self, text: str) -> None:
        self.text = text
        self.move_cursor(self.document.end)
