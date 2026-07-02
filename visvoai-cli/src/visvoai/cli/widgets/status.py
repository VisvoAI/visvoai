"""StatusBar — the single bottom line: progress on the left, context on the right.

Replaces the top header and the shortcut footer. Left side shows the model when
idle, or a live progress message during a turn (`set_status`). Right side shows
the location (cwd + git branch).
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme

# Thinking level → readable label for the footer.
_THINK_LABEL = {"off": "Off", "low": "Low", "medium": "Medium", "high": "High"}


def fmt_tokens(n: int) -> str:
    """Compact token count for the footer: 950 → '950', 45200 → '45.2K', 1.2M → '1.2M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class StatusBar(Horizontal):
    """Bottom bar. The mode chip and the processes chip are CLICKABLE (cycle
    mode / open /ps) — they're separate child Statics so they get real hit
    areas; the app handles the posted messages."""

    class ModeChipClicked(Message):
        pass

    class ProcsChipClicked(Message):
        pass

    DEFAULT_CSS = """
    StatusBar { height: 1; padding: 0 1; }
    StatusBar > #sb-mode { width: auto; }
    StatusBar > #sb-left { width: 1fr; }
    StatusBar > #sb-procs { width: auto; }
    StatusBar > #sb-right { width: auto; content-align: right middle; }
    """

    def __init__(self, model: str = "", location: str = "", id: str | None = None) -> None:
        super().__init__(id=id)
        self._model = model              # fallback plain label (used until set_model_line)
        self._model_rich: dict | None = None   # {name, provider, level, in_cost, out_cost}
        self._location = location
        self._status: str | None = None
        self._context_pct: int | None = None  # None → gauge hidden
        self._context_tokens: int | None = None  # raw tokens in context (shown as the label)
        self._cost: float = 0.0               # cumulative conversation cost (USD)
        self._mode: str | None = None  # None | "plan" | "read-only" — a left chip
        self._processes: int = 0       # running background processes (0 → chip hidden)

    def compose(self) -> ComposeResult:
        yield _ModeChip(id="sb-mode")
        yield Static(id="sb-left")
        yield _ProcsChip(id="sb-procs")
        yield Static(id="sb-right")

    def on_mount(self) -> None:
        self._render_bar()

    def set_status(self, text: str | None) -> None:
        """Show a transient progress message on the left; None reverts to model."""
        self._status = text
        self._render_bar()

    def set_model(self, model: str) -> None:
        """Plain fallback label (e.g. a raw id when no view is available)."""
        self._model = model
        self._model_rich = None
        self._render_bar()

    def set_model_line(self, name: str, level: str | None,
                       in_cost: float, out_cost: float) -> None:
        """The rich idle model line: dot + display name + thinking + cost."""
        self._model_rich = {
            "name": name, "level": level, "in_cost": in_cost, "out_cost": out_cost,
        }
        self._render_bar()

    def _model_text(self, tv: dict) -> Text:
        """Build the idle model line — rich when set_model_line was used, else the
        plain fallback label."""
        t = Text()
        r = self._model_rich
        if r is None:
            t.append(self._model, style=tv["muted"])
            return t
        t.append("● ", style=tv["primary"])
        t.append(r["name"], style=tv["foreground"])
        if r["level"]:
            label = _THINK_LABEL.get(r["level"], r["level"].title())
            t.append(f" ({label})", style=f"dim {tv['muted']}")
        t.append(f" | ${r['in_cost']:g}/${r['out_cost']:g} per 1M tks",
                 style=f"dim {tv['muted']}")
        return t

    def set_mode(self, mode: str | None) -> None:
        """Show a mode chip on the left ('plan' / 'read-only'), or None to clear.
        Signals the agent won't edit yet — the user unlocks execution elsewhere."""
        self._mode = mode
        self._render_bar()

    def set_context(self, pct: int | None, tokens: int | None = None) -> None:
        """Set the % of the context window used (0–100), or None to hide the gauge.
        `tokens` is the raw token count shown as the label (None → no count)."""
        self._context_pct = None if pct is None else max(0, min(100, pct))
        self._context_tokens = None if pct is None else tokens
        self._render_bar()

    def set_cost(self, usd: float) -> None:
        """Set the cumulative conversation cost (USD) shown on the right rail."""
        self._cost = usd
        self._render_bar()

    def set_processes(self, count: int) -> None:
        """Number of running background processes; a right-rail chip when > 0 so
        the user always knows something is running (and can /ps to manage it)."""
        self._processes = max(0, count)
        self._render_bar()

    def restyle(self) -> None:
        self._render_bar()

    CTX_BAR_W = 9   # fixed-width context gauge cell

    def _context_label(self, tv: dict) -> Text:
        """A fixed-width gauge cell with the % CENTERED INSIDE it: the left portion
        fills (coloured bg) proportional to context used, the rest is a dim track.
        Colour escalates as it fills (green → amber → red)."""
        pct = self._context_pct
        # On-brand accent while there's headroom; escalate only in the danger zone.
        fill_color = tv["secondary"] if pct < 75 else tv["warning"] if pct < 90 else tv["error"]
        label = f"{pct}%".center(self.CTX_BAR_W)
        fill = round(pct / 100 * self.CTX_BAR_W)
        t = Text()
        for i, ch in enumerate(label):
            if i < fill:
                t.append(ch, style=f"bold {tv['background']} on {fill_color}")  # filled
            else:
                t.append(ch, style=f"{tv['muted']} on {tv['panel']}")          # track
        return t

    def _render_bar(self) -> None:
        # The bar's child Statics exist only between compose and unmount; a status/
        # context update racing teardown would otherwise raise NoMatches.
        try:
            mode_cell = self.query_one("#sb-mode", Static)
            left_cell = self.query_one("#sb-left", Static)
            procs_cell = self.query_one("#sb-procs", Static)
            right_cell = self.query_one("#sb-right", Static)
        except NoMatches:
            return
        tv = theme.palette(self)
        mode = Text()
        if self._mode is not None:
            # A reverse-video chip so the active mode is unmissable. Clickable: cycles.
            mode.append(f" ◆ {self._mode} ", style=f"bold {tv['warning']} reverse")
            mode.append("  ", style=tv["muted"])
        mode_cell.update(mode)
        left = Text()
        if self._status:
            left.append(self._status, style=tv["secondary"])
        else:
            left.append_text(self._model_text(tv))
        left_cell.update(left)
        procs = Text()
        if self._processes > 0:
            procs.append(f"⏵ {self._processes} proc{'s' if self._processes != 1 else ''}",
                         style=tv["secondary"])
            procs.append(" /ps", style=f"dim {tv['muted']}")
            procs.append("   ", style=tv["muted"])
        procs_cell.update(procs)
        right = Text()
        if self._cost > 0:
            right.append("~$", style=f"dim {tv['muted']}")
            right.append(f"{self._cost:.4f}", style=tv["secondary"])
            right.append("   ", style=tv["muted"])
        if self._context_pct is not None:
            # The token count consumed so far is the label; the gauge carries the %.
            if self._context_tokens is not None:
                right.append(f"{fmt_tokens(self._context_tokens)} tokens ",
                             style=f"dim {tv['muted']}")
            right.append_text(self._context_label(tv))
            right.append("   ", style=tv["muted"])
        right.append(self._location, style=tv["muted"])
        right_cell.update(right)


class _ModeChip(Static):
    def on_click(self) -> None:
        self.post_message(StatusBar.ModeChipClicked())


class _ProcsChip(Static):
    def on_click(self) -> None:
        self.post_message(StatusBar.ProcsChipClicked())
