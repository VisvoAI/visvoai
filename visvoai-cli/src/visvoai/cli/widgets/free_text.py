"""FreeText — inline free-text clarification HITL (claude-code style).

The agent's open question rendered bold above a single multi-line input area. The
user types a free-form answer (a URL, a pasted traceback, a prose description) —
unlike `Selection` (choice) or `Form` (named fields). Enter submits; Ctrl+J /
Opt+Enter insert a newline; Esc cancels. An empty submit is a no-op (an open
question must get real text, never "").

`ask()` resolves to the entered text (stripped) on submit, or `None` on cancel /
unmount-mid-prompt. This is the primitive the clarification loop (ask → answer →
re-ask sharper) is built on.
"""
from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli.widgets.form import FieldArea


class FreeText(Vertical):
    """Inline free-text prompt; await `.ask()` for `str | None`."""

    DEFAULT_CSS = """
    FreeText {
        background: transparent;
        padding: 0 1;
        margin: 0;
        height: auto;
    }
    FreeText .ft-prompt { text-style: bold; color: $foreground; margin: 0; padding: 0 0 0 2; }
    FreeText .ft-hint { color: $muted; margin: 0; padding: 0 0 0 2; }
    /* No underline/box/fill, and no focus restyle (pin :focus to the base). */
    FreeText > FieldArea, FreeText > FieldArea:focus {
        height: auto;
        max-height: 6;
        border: none;
        background: transparent;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, prompt: str, placeholder: str = "", multiline: bool = True) -> None:
        super().__init__()
        self.prompt = prompt
        self.placeholder = placeholder
        # `multiline=False` (single-line, Enter submits, no newline) is a stub for the
        # composable spec to use later — both paths reuse FieldArea for now.
        self.multiline = multiline
        self._future: asyncio.Future | None = None

    def compose(self) -> ComposeResult:
        yield Static(self.prompt, classes="ft-prompt")
        yield FieldArea("text", self.placeholder)
        yield Static(
            "[b]enter[/] submit   [b]Ctrl+J[/] newline   [b]esc[/] cancel",
            classes="ft-hint",
        )

    def on_mount(self) -> None:
        field = self.query(FieldArea).first()
        if field is not None:
            field.focus()

    def on_unmount(self) -> None:
        if self._future and not self._future.done():
            self._future.set_result(None)

    def ask(self) -> asyncio.Future:
        self._future = asyncio.get_running_loop().create_future()
        return self._future

    def _resolve(self, result) -> None:
        if self._future and not self._future.done():
            self._future.set_result(result)

    def on_field_area_next(self, event: FieldArea.Next) -> None:
        event.stop()
        text = event.field.text.strip()
        if not text:
            return  # empty submit is a no-op — an open question must get real text
        self._resolve(text)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self._resolve(None)
            event.stop()
