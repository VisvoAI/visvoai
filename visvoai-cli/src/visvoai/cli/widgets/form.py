"""Form — inline multi-field HITL (claude-code style).

For questions that need more than a single choice: a stack of labeled multi-line
fields mounted inline in the conversation. Enter advances to the next field
(submits on the last); Ctrl+J / Opt+Enter inserts a newline; Esc cancels.
`ask()` resolves to a `{key: value}` dict, or `None` if cancelled.
"""
from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, TextArea

from visvoai.cli.widgets.textarea_guard import StyleRaceGuard


class FieldArea(StyleRaceGuard, TextArea):
    """A multi-line form field. Enter advances (Form decides next/submit);
    Ctrl+J / Opt+Enter insert a newline."""

    class Next(Message):
        def __init__(self, field: "FieldArea") -> None:
            self.field = field
            super().__init__()

    def __init__(self, key: str, placeholder: str, default: str = "") -> None:
        super().__init__(text=default, placeholder=placeholder, soft_wrap=True)
        self.key = key

    async def _on_key(self, event) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.Next(self))
            return
        if event.key in ("ctrl+j", "alt+enter", "shift+enter"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        await super()._on_key(event)


class FormField(Vertical):
    """One labeled multi-line field. `key` identifies it in the resolved dict."""

    DEFAULT_CSS = """
    FormField { height: auto; margin: 0; }
    /* label + field align to the grid content column (padding-left = grid.GUTTER). */
    FormField > .field-label { color: $primary; text-style: bold; padding: 0 0 0 2; }
    /* No underline/box/fill, and no focus restyle (pin :focus to the base). */
    FormField > FieldArea, FormField > FieldArea:focus {
        height: auto;
        max-height: 6;
        border: none;
        background: transparent;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, key: str, label: str, placeholder: str = "", default: str = "") -> None:
        super().__init__()
        self.key = key
        self.label = label
        self.placeholder = placeholder
        self.default = default

    def compose(self) -> ComposeResult:
        yield Static(self.label, classes="field-label")
        yield FieldArea(self.key, self.placeholder, self.default)


class Form(Vertical):
    """Inline multi-field prompt; await `.ask()` for `{key: value} | None`."""

    DEFAULT_CSS = """
    /* Class-6 identity: the warning rail — a blocking ask must read as one at
       a glance (see Selection for the full rationale). */
    Form {
        background: $warning 8%;
        border-left: outer $warning 70%;
        padding: 0 1;
        margin: 0;
        height: auto;
    }
    Form .form-prompt { text-style: bold; color: $foreground; margin: 0; padding: 0 0 0 2; }
    Form .form-hint { color: $muted; margin: 0; padding: 0 0 0 2; }
    """

    def __init__(self, prompt: str, fields: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self.prompt = prompt
        # fields: list of (key, label, placeholder)
        self.fields = fields
        self._future: asyncio.Future | None = None

    def compose(self) -> ComposeResult:
        yield Static(self.prompt, classes="form-prompt")
        for key, label, placeholder in self.fields:
            yield FormField(key, label, placeholder)
        yield Static(
            "[b]enter[/] next / submit   [b]Ctrl+J[/] newline   [b]esc[/] cancel",
            classes="form-hint",
        )

    def on_mount(self) -> None:
        first = self.query(FieldArea).first()
        if first is not None:
            first.focus()

    def on_unmount(self) -> None:
        if self._future and not self._future.done():
            self._future.set_result(None)

    def ask(self) -> asyncio.Future:
        self._future = asyncio.get_running_loop().create_future()
        return self._future

    def _values(self) -> dict[str, str]:
        return {f.key: f.query_one(FieldArea).text for f in self.query(FormField)}

    def _resolve(self, result) -> None:
        if self._future and not self._future.done():
            self._future.set_result(result)

    def on_field_area_next(self, event: FieldArea.Next) -> None:
        event.stop()
        fields = list(self.query(FieldArea))
        idx = fields.index(event.field)
        if idx < len(fields) - 1:
            fields[idx + 1].focus()  # advance to next field
        else:
            self._resolve(self._values())  # last field → submit

    def on_key(self, event) -> None:
        if event.key == "escape":
            self._resolve(None)
            event.stop()
