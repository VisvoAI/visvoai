"""Conversation-stream widgets: UserMsg, Assistant, Thinking, TurnFooter.

Each owns its styling via DEFAULT_CSS so it renders consistently wherever mounted.
(Launch chrome — Welcome/WelcomeBanner — lives in welcome.py.)
"""
from __future__ import annotations

import time

from rich.text import Text
from textual.widgets import Markdown, Static

from visvoai.cli import grid, theme


class UserMsg(Static):
    """The user's prompt — the turn anchor. Uses the SAME `❯` marker as the main
    input (so a sent message visually echoes the prompt) on a subtle primary wash,
    with a blank line above and below so each turn reads as a distinct, scannable
    header."""

    DEFAULT_CSS = """
    UserMsg {
        background: $primary 10%;   /* subtle wash — differential, not loud */
        margin: 1 0;               /* one blank line before AND after the anchor */
        padding: 1;                /* roomy card: a washed line above/below + side pad */
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def render(self) -> Text:
        tv = theme.palette(self)
        t = grid.gutter("❯", tv["primary"])           # same marker as the input
        t.append(self._text, style=tv["foreground"])  # normal weight (not bold)
        return t


class Assistant(Markdown):
    """Streaming assistant reply, rendered as markdown.

    Subclasses Textual's `Markdown` widget so replies render the real shape of
    model output — headings, lists, bold/italic, inline code, tables, blockquotes,
    and **fenced code blocks with syntax highlighting** (the fence re-highlights
    itself on a theme switch natively). Tokens stream in via `await add(token)`,
    which calls `Markdown.append()` — an incremental parse that only re-renders the
    tail block, so streaming stays cheap and partial fences render gracefully.

    The default Markdown chrome is flattened to match the app's borderless look:
    headers are left-aligned bold $primary with no background panel.
    """

    DEFAULT_CSS = """
    /* Blank gutter: the answer carries no marker, so its content indents to the
       grid content column (padding-left = grid.CONTENT = 3). */
    Assistant {
        background: transparent;
        margin: 0;
        padding: 0 1 0 3;
    }
    Assistant MarkdownH1, Assistant MarkdownH2, Assistant MarkdownH3,
    Assistant MarkdownH4, Assistant MarkdownH5, Assistant MarkdownH6 {
        background: transparent;
        color: $primary;
        text-style: none;   /* distinguished by colour, not heavy bold */
        content-align: left middle;
        width: 1fr;
        margin: 1 0 0 0;
        padding: 0;
    }
    /* Fenced code blocks: a subtle accent wash + padding so the block reads as a
       contained unit in BOTH light and dark (Textual's default leaves it bg-less,
       which vanishes on a light terminal). */
    Assistant MarkdownFence {
        margin: 1 0;
        padding: 0 1;
        background: $primary 10%;
    }
    Assistant MarkdownBlockQuote {
        background: transparent;
        border-left: outer $primary 50%;
    }
    /* Inline `code`: on-brand (a faint primary wash + secondary text), replacing
       Textual's default amber/warning tint which clashes with the palette. The
       :dark/:light variants are needed to outrank Textual's mode-scoped default. */
    Assistant MarkdownBlock:dark .code_inline,
    Assistant MarkdownBlock:light .code_inline {
        background: $primary 12%;
        color: $secondary;
    }
    /* Tables: prominent grid lines (Textual's default is $foreground 20% — washed
       out). Full $foreground reads clean and crisp. */
    Assistant MarkdownTableContent { keyline: thin $foreground; }
    /* Kill the paragraph's trailing margin so it doesn't COMPOUND with the
       between-group gap (was producing a 2-line gap after the answer). */
    Assistant MarkdownParagraph { margin: 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._raw = ""   # accumulated markdown source (Markdown.append keeps none)

    async def add(self, token: str) -> None:
        self._raw += token
        await self.append(token)


class WorkingIndicator(Static):
    """A transient spinner shown the instant a turn starts, so there's never a dead
    gap before the first output. Removed as soon as real content/thinking/a tool
    arrives — so it only ever lives during the initial wait. Two lines: spinner +
    label, then a muted tip that rotates every ~12s and teaches a discoverable
    feature. Each new indicator opens on the NEXT tip so variety builds across turns."""

    FRAMES = "⠋⠙⠹⠸⠼⠴▴▾◂▸"
    TIP_INTERVAL = 12.0

    # One rotating pool. Short (one line on 80 cols) and action-oriented — the user
    # is waiting, not reading; the tip teaches by sitting next to the spinner.
    TIPS: tuple[str, ...] = (
        "every turn auto-saves a checkpoint — /rewind to undo, /branch to fork",
        "esc stops the current turn mid-stream",
        "@file attaches a file to your message",
        "type / for commands — try /help for everything",
        "shift+tab cycles approval mode — auto-edit allows writes but still asks before shell",
        "click a ✦ thought block to expand the model's reasoning",
        "tools ask before mutating — approve once, allow-all-session, or deny",
        "writes stay inside your project; [permissions] in .visvoai/config.toml can pre-authorize",
        "/log lists the checkpoints your work was auto-saved at",
    )
    _next_start = 0   # class-level cursor → consecutive turns open on different tips

    DEFAULT_CSS = """
    WorkingIndicator { color: $secondary; margin: 0; padding: 0 1; background: transparent; }
    """

    def __init__(self, label: str = "working…") -> None:
        super().__init__()
        self._label = label
        self._i = 0
        cls = type(self)
        self._tip_index = cls._next_start % len(self.TIPS)
        cls._next_start += 1
        self._tip = self.TIPS[self._tip_index]

    def on_mount(self) -> None:
        self._tick_timer = self.set_interval(0.08, self._tick_frame)
        self._tip_timer = self.set_interval(self.TIP_INTERVAL, self._tick_tip)
        self.refresh()

    def _tick_frame(self) -> None:
        self._i += 1
        self.refresh()

    def _tick_tip(self) -> None:
        self._tip_index = (self._tip_index + 1) % len(self.TIPS)
        self._tip = self.TIPS[self._tip_index]
        self.refresh()

    def render(self) -> Text:
        tv = theme.palette(self)
        muted = tv.get("muted") or tv.get("foreground")
        frame = self.FRAMES[self._i % len(self.FRAMES)]
        t = grid.gutter(frame, tv["secondary"])
        t.append(self._label, style=tv["secondary"])
        # Tip line: indented to the content column, a 💡 marker, then the text.
        # muted may be absent on some themes → fall back to foreground so we never
        # emit `[dim None]` markup.
        t.append("\n")
        t.append(grid.INDENT)
        t.append("💡 ", style=tv["secondary"])
        t.append(self._tip, style=f"dim {muted}")
        return t

    def stop(self) -> None:
        for attr in ("_tick_timer", "_tip_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                t.stop()
                setattr(self, attr, None)

    def on_unmount(self) -> None:
        self.stop()


class TurnFooter(Static):
    """A muted one-line receipt after a turn: duration · model · thinking level.
    Lives only in the transcript UI — NEVER added to the message history, so it
    stays out of the model's context (and models can differ across turns)."""

    DEFAULT_CSS = """
    TurnFooter { color: $muted; margin: 0; padding: 0 1; background: transparent; }
    """

    def __init__(self, summary: str) -> None:
        super().__init__()
        self._summary = summary

    def render(self) -> Text:
        tv = theme.palette(self)
        t = grid.gutter("✦", f"dim {tv['muted']}")
        t.append(self._summary, style=f"dim {tv['muted']}")
        return t


class Thinking(Static):
    """The agent's reasoning, collapsed by default. While active it shows only a
    spinner + 'thinking…' (text hidden); when done() it collapses to a clickable
    '✦ thought for <duration>' summary. Clicking expands/collapses the reasoning
    text. Stays on screen (distinct muted left bar) — never removed."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    DEFAULT_CSS = """
    Thinking {
        color: $muted;
        margin: 0;
        padding: 0 1;   /* gutter block: glyph at col 1, content at col 3 */
        background: transparent;
    }
    Thinking:hover { background: $hover; }   /* clickable once finished */
    """

    def __init__(self) -> None:
        super().__init__()
        self._buf = ""
        self._active = True
        self._i = 0
        self._expanded = False
        self._hover = False
        self._start = time.monotonic()
        self._elapsed: float | None = None   # set on done(); None for a replayed block

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.08, self._tick)
        self.refresh()

    def add(self, token: str) -> None:
        self._buf += token
        if self._expanded:
            self.refresh()  # only redraw body if it's actually visible

    def _tick(self) -> None:
        self._i += 1
        self.refresh()

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m {s % 60}s"
        return f"{s // 3600}h {(s % 3600) // 60}m"

    def render(self) -> Text:
        tv = theme.palette(self)
        if self._active:
            frame = self.FRAMES[self._i % len(self.FRAMES)]
            t = grid.gutter(frame, tv["secondary"])
            t.append("Thinking…", style=tv["secondary"])
        else:
            # On hover (finished → clickable) brighten the whole summary so the
            # affordance is unmistakable; otherwise it sits quietly dimmed.
            hov = self._hover
            glyph_style = tv["secondary"] if hov else f"dim {tv['muted']}"
            label_style = tv["foreground"] if hov else f"dim {tv['muted']}"
            hint_style = tv["secondary"] if hov else f"dim {tv['muted']}"
            label = f"Thought for {self._fmt(self._elapsed)}" if self._elapsed is not None else "Thought"
            t = grid.gutter("✦", glyph_style)
            t.append(label, style=label_style)
            if self._buf:   # consistent with tools: a text hint, not a caret
                hint = "(click to collapse)" if self._expanded else "(click to expand)"
                t.append(f"   {hint}", style=hint_style)
        if self._expanded and self._buf:
            # Align EVERY reasoning line to the grid content column (not just the
            # first) so the body reads as a clean indented block, not a ragged dump.
            body = "\n".join(grid.INDENT + ln for ln in self._buf.splitlines())
            t.append("\n")
            t.append(body, style=f"dim italic {tv['muted']}")
        return t

    def done(self) -> None:
        """Stop the spinner, record duration, collapse to a summary (kept)."""
        self._elapsed = time.monotonic() - self._start
        self._active = False
        self.stop()
        self.refresh()

    def restore(self, text: str, elapsed: float | None = None) -> None:
        """Populate a finished reasoning block from saved history (replay) — already
        collapsed. `elapsed` (from the saved receipt) shows 'Thought for Xs'; None
        falls back to a plain 'Thought'."""
        self._buf = text
        self._active = False
        self._elapsed = elapsed if elapsed else None
        self.stop()
        self.refresh()

    def on_enter(self, event) -> None:
        if not self._active:
            self._hover = True
            self.refresh()

    def on_leave(self, event) -> None:
        if self._hover:
            self._hover = False
            self.refresh()

    def on_click(self) -> None:
        if self._active:
            return  # only expandable once thinking has finished
        self._expanded = not self._expanded
        # layout=True so the widget re-measures its auto height — otherwise a
        # collapse leaves behind the empty space the expanded text occupied.
        self.refresh(layout=True)

    def stop(self) -> None:
        if getattr(self, "_timer", None):
            self._timer.stop()
            self._timer = None

    def on_unmount(self) -> None:
        """Stop the interval on unmount so it doesn't fire on a torn-down widget."""
        self.stop()
