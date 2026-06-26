"""Selection — inline HITL (claude-code style): keyboard + mouse choice list.

A prompt + navigable options (↑/↓ or click), a `(recommended)` tag. Tab on an
option enters TRUE INLINE edit mode: the option's own line becomes
`❯ <label> · <note>▏` and keystrokes edit the note directly (no input box).
Enter saves, Esc cancels. Resolves an awaitable future to `(index | None, note)`
where `note` is the active option's saved note.

When mounted directly after a `CleanDiff` in the same parent, the Selection
attaches visually (shared border edge, no gap) so they look like one piece.
"""
from __future__ import annotations

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import grid, theme


class OptionRow(Static):
    """One option row, rendered in place. Tab edits its note inline — the row
    draws `❯ label · note▏` and consumes keystrokes itself (no Input widget),
    so it never looks like a separate text box."""

    can_focus = True

    DEFAULT_CSS = """
    OptionRow { padding: 0; height: 1; }   /* gutter block: ❯ at col 1, label at col 3 */
    /* No background bar for the active/hover row — the ❯ marker + accent label carry
       the selection (a full-width highlight reads as an eyesore). Only an in-progress
       note edit gets a subtle fill so the editing row is unmistakable. */
    OptionRow.editing { background: $hover; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, label: str, recommended: bool) -> None:
        super().__init__()
        self.index = index
        self.label = label
        self.recommended = recommended
        self.note = ""
        self._active = False
        self._editing = False
        self._buf = ""

    def render(self) -> Text:
        tv = theme.palette(self)
        hot = self._active or self._editing
        t = grid.gutter("❯" if hot else " ", tv["primary"] if hot else "dim")
        # A leading number (1-based) — always visible, so the list reads as choices
        # you can also press a digit to pick.
        t.append(f"{self.index + 1}. ", style=tv["primary"] if hot else tv["muted"])
        t.append(self.label, style=f"bold {tv['primary']}" if hot else tv["foreground"])
        if self._editing:
            t.append("  · ", style=f"dim {tv['muted']}")
            t.append(self._buf, style=f"italic {tv['foreground']}")
            t.append("▏", style=tv["primary"])  # inline caret
            if not self._buf:
                t.append("  add a note — enter saves, esc cancels", style=f"dim {tv['muted']}")
        else:
            if self.recommended:
                t.append("   (recommended)", style=f"dim {tv['success']}")
            if self.note:
                t.append(f"   · {self.note}", style=f"italic {tv['muted']}")
        return t

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self.refresh()

    def is_editing(self) -> bool:
        return self._editing

    def enter_edit_mode(self) -> None:
        self._editing = True
        self._buf = self.note
        self.add_class("editing")
        self.focus()
        self.refresh()

    def _exit_edit_mode(self, save: bool) -> None:
        if save:
            self.note = self._buf.strip()
        self._editing = False
        self._buf = ""
        self.remove_class("editing")
        self.refresh()
        if self.parent and self.parent.can_focus:
            self.parent.focus()  # hand focus back to the Selection for nav

    def on_click(self) -> None:
        if self._editing:
            return
        self.post_message(self.Chosen(self.index))

    def on_key(self, event) -> None:
        if not self._editing:
            return
        if event.key == "enter":
            self._exit_edit_mode(save=True)
        elif event.key == "escape":
            self._exit_edit_mode(save=False)
        elif event.key == "backspace":
            self._buf = self._buf[:-1]
            self.refresh()
        elif event.character and event.character.isprintable():
            self._buf += event.character
            self.refresh()
        event.stop()  # while editing, the row owns every key


class Selection(Vertical):
    """Inline choice prompt; await `.ask()` for `(index | None, note)`.

    Tab on the active option enters inline edit mode for that OptionRow. The
    note is stored on the OptionRow; on resolution, the Selection captures the
    active option's note as its own.
    """

    can_focus = True

    DEFAULT_CSS = """
    /* No borders: identity comes from the bold prompt + the ❯ option markers. This
       lets a tool-approval Selection sit FLUSH under its diff (one connected group)
       instead of being walled off by a divider. */
    Selection {
        background: transparent;
        padding: 0 1;
        margin: 0;
        height: auto;
        /* Short approval lists stay compact (height: auto); long lists (e.g. the
           model picker) cap here and scroll internally so they never overflow the
           screen. _sync keeps the highlighted row in view. */
        max-height: 14;
        overflow-y: auto;
    }
    /* prompt + hint align to the grid content column (padding-left = grid.GUTTER). */
    Selection .sel-prompt { text-style: bold; color: $foreground; margin: 0; padding: 0 0 0 2; }
    Selection .sel-hint { color: $muted; margin: 0; padding: 0 0 0 2; }
    """

    def __init__(self, prompt: str, options: list[str], recommended: int = 0,
                 compact: bool = False) -> None:
        super().__init__()
        self.prompt = prompt
        self.options = options
        self.recommended = recommended
        # Expedited approval: drop the hint line so a trivial gate (a one-line
        # guard fix) doesn't carry the full multi-line approval chrome.
        self.compact = compact
        self.idx = 0
        self.note = ""
        self._future: asyncio.Future | None = None

    def compose(self) -> ComposeResult:
        yield Static(self.prompt, classes="sel-prompt")
        for i, opt in enumerate(self.options):
            yield OptionRow(i, opt, recommended=(i == self.recommended))
        if not self.compact:
            yield Static(
                "[b]↑/↓[/] navigate   [b]enter[/]/click select   [b]tab[/] note   [b]esc[/] cancel",
                classes="sel-hint",
            )

    def on_mount(self) -> None:
        self.focus()
        self._sync()

    def on_unmount(self) -> None:
        """Resolve any pending future (e.g. app closed mid-prompt)."""
        if self._future and not self._future.done():
            self._future.set_result((None, self.note))

    def _rows(self) -> list[OptionRow]:
        return list(self.query(OptionRow))

    def _sync(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_active(i == self.idx)
        # Keep the active option visible when the list is taller than max-height
        # (the model picker can have many entries) so ↑/↓ never navigates blind.
        if rows and 0 <= self.idx < len(rows):
            rows[self.idx].scroll_visible(animate=False)

    def _any_editing(self) -> bool:
        return any(r.is_editing() for r in self._rows())

    def ask(self) -> asyncio.Future:
        self._future = asyncio.get_running_loop().create_future()
        return self._future

    def _resolve(self, result) -> None:
        if self._future and not self._future.done():
            self._future.set_result(result)

    def on_option_row_chosen(self, msg: OptionRow.Chosen) -> None:
        self.idx = msg.index
        self._sync()
        self._capture_active_note()
        self._resolve((self.idx, self.note))

    def _capture_active_note(self) -> None:
        rows = self._rows()
        if rows:
            self.note = rows[self.idx].note

    def on_key(self, event) -> None:
        # While an option is in inline edit mode, the Input owns all keys
        # (chars, enter→save, esc→cancel via OptionRow). Don't let bubbling
        # keys reach the selection logic and resolve/navigate underneath it.
        if self._any_editing():
            return
        if event.character and event.character.isdigit() and event.character != "0":
            n = int(event.character)
            if n <= len(self.options):
                self.idx = n - 1; self._sync()
                self._capture_active_note()
                self._resolve((self.idx, self.note)); event.stop()
            return
        if event.key in ("up", "k"):
            self.idx = (self.idx - 1) % len(self.options); self._sync(); event.stop()
        elif event.key in ("down", "j"):
            self.idx = (self.idx + 1) % len(self.options); self._sync(); event.stop()
        elif event.key == "enter":
            self._capture_active_note()
            self._resolve((self.idx, self.note)); event.stop()
        elif event.key == "tab":
            # Enter edit mode on the active option (if not already editing)
            if not self._any_editing():
                rows = self._rows()
                if rows:
                    rows[self.idx].enter_edit_mode()
            event.stop()
        elif event.key == "escape":
            self._resolve((None, self.note)); event.stop()