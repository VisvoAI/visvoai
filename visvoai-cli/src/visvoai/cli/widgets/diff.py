"""CleanDiff — delta/GitHub-style diff: line-number gutter + full-line bg tints.

Renders a list of (kind, code) lines where kind ∈ {"ctx", "add", "del"}. No raw
git language (`@@`, `---/+++`); just clean +/- with a gutter and tinted rows.
"""
from __future__ import annotations

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.widgets.output import ShowMore


class DiffLine(Static):
    """A single diff row; its CSS class supplies the full-width background tint."""

    DEFAULT_CSS = """
    DiffLine { height: 1; width: 1fr; }
    DiffLine.diff-add { background: $diff-add-bg; }
    DiffLine.diff-del { background: $diff-del-bg; }
    """


class CleanDiff(Vertical):
    """Borderless diff block: a filename + counts header line, then tinted rows
    (the +/- tints carry the block shape; a subtle left bar groups it)."""

    DEFAULT_CSS = """
    /* Tool body: aligns under the tool header's content (padding-left = grid.CONTENT). */
    CleanDiff {
        background: transparent;
        padding: 0 0 0 3;
        margin: 0;
        height: auto;
    }
    CleanDiff > .diff-header { height: 1; padding: 0; }
    """

    # Side-by-side needs roughly this many cells of content width; below it we
    # fall back to the unified single column so neither side gets cramped.
    SIDE_BY_SIDE_MIN_WIDTH = 90

    def __init__(
        self,
        filename: str,
        changes: list[tuple[str, str]],
        max_lines: int | None = None,
        diff_layout: str = "auto",   # "auto" | "side" | "unified"
        show_header: bool = False,   # the filename/counts header — off when a tool/git
                                     # body already names the file (avoids duplication)
    ) -> None:
        super().__init__()
        self.filename = filename
        self.changes = changes
        self.max_lines = max_lines
        self.diff_layout = diff_layout
        self.show_header = show_header
        self._expanded = False
        self._built_layout: str | None = None

    def _effective_layout(self) -> str:
        """Resolve the layout. Side-by-side only earns its keep when there are
        BOTH additions and deletions to pair across the divider — a pure-add or
        pure-del diff leaves one column empty, so it falls back to unified. Then
        width gates it (narrow → unified)."""
        if self.diff_layout == "unified":
            return "unified"
        adds = any(k == "add" for k, _ in self.changes)
        dels = any(k == "del" for k, _ in self.changes)
        if not (adds and dels):
            return "unified"   # nothing to pair → side-by-side would be lopsided
        width = self.size.width or (self.app.size.width - 8 if self.is_mounted else 80)
        return "side" if width >= self.SIDE_BY_SIDE_MIN_WIDTH else "unified"

    def _highlighter(self) -> Syntax | None:
        """A Rich `Syntax` keyed to the file's language + current mode, or None when
        the language is unknown. ANSI themes pull colors from the terminal palette,
        so highlighting blends with the rest of the UI and re-themes on a switch."""
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_for_filename(self.filename)
        except ClassNotFound:
            return None
        _, mode = theme.parse_theme(self.app.theme)
        return Syntax("", lexer, theme="ansi_light" if mode == "light" else "ansi_dark")

    def _code(self, syntax: Syntax | None, code: str, fallback: str) -> Text:
        """Syntax-highlight a code string; fall back to a flat style for context
        lines or unknown languages."""
        if not code or syntax is None:
            return Text(code, style=fallback)
        t = syntax.highlight(code)
        t.rstrip()  # Syntax.highlight appends a trailing newline
        return t

    def _build_lines(self) -> list[DiffLine]:
        tv = theme.palette(self)
        syntax = self._highlighter()
        rows: list[DiffLine] = []
        ln = 1
        for kind, code in self.changes:
            t = Text()
            if kind == "add":
                t.append(f" {ln:>3} ", style="dim")
                t.append("+ ", style=f"bold {tv['success']}")
                t.append_text(self._code(syntax, code, tv["foreground"]))
                rows.append(DiffLine(t, classes="diff-add"))
                ln += 1
            elif kind == "del":
                t.append("     ", style="dim")
                t.append("- ", style=f"bold {tv['error']}")
                t.append_text(self._code(syntax, code, tv["foreground"]))
                rows.append(DiffLine(t, classes="diff-del"))
            else:
                # Context lines stay muted (un-highlighted) so the +/- changes pop.
                t.append(f" {ln:>3} ", style="dim")
                t.append("  ", style="dim")
                t.append(code, style=tv["muted"])
                rows.append(DiffLine(t, classes="diff-ctx"))
                ln += 1
        return rows

    def _cell(self, syntax, ln, sign, code, width: int, tv: dict,
              ctx: bool, bg: str | None) -> Text:
        """One side of a side-by-side row: `ln sign code`, padded/truncated to
        `width`, with an optional full-cell background tint for a changed line."""
        t = Text()
        t.append(f"{ln:>3} " if ln else "    ", style="dim")
        if sign:
            color = tv["success"] if sign == "+" else tv["error"]
            t.append(f"{sign} ", style=f"bold {color}")
        else:
            t.append("  ", style="dim")
        if ctx or not code:
            t.append(code, style=tv["muted"])
        else:
            t.append_text(self._code(syntax, code, tv["foreground"]))
        t.truncate(width, overflow="ellipsis", pad=True)
        if bg:
            t.stylize(f"on {bg}")
        return t

    def _build_side(self) -> list[DiffLine]:
        """Side-by-side: before / after, paired per line. The two panes separate by
        a 3-space gap (the add/del background washes carry the split) — the old │
        divider column rendered as broken dashes on line-spaced terminals."""
        tv = theme.palette(self)
        syntax = self._highlighter()
        width = self.size.width or 90
        side = max(20, (width - 3) // 2)   # 3 = the inter-pane gap
        add_bg, del_bg = tv["diff-add-bg"], tv["diff-del-bg"]
        rows: list[DiffLine] = []
        ln_l = ln_r = 1
        i, n = 0, len(self.changes)
        while i < n:
            kind, code = self.changes[i]
            if kind == "ctx":
                left = self._cell(syntax, ln_l, "", code, side, tv, ctx=True, bg=None)
                right = self._cell(syntax, ln_r, "", code, side, tv, ctx=True, bg=None)
                ln_l += 1; ln_r += 1; i += 1
            else:
                dels, adds = [], []
                while i < n and self.changes[i][0] == "del":
                    dels.append(self.changes[i][1]); i += 1
                while i < n and self.changes[i][0] == "add":
                    adds.append(self.changes[i][1]); i += 1
                rows.extend(self._paired(syntax, dels, adds, side, tv,
                                         add_bg, del_bg, ln_l, ln_r))
                ln_l += len(dels); ln_r += len(adds)
                continue
            row = left + Text("   ") + right
            rows.append(DiffLine(row, classes="diff-ctx"))
        return rows

    def _paired(self, syntax, dels, adds, side, tv, add_bg, del_bg, ln_l, ln_r):
        rows = []
        for k in range(max(len(dels), len(adds))):
            if k < len(dels):
                left = self._cell(syntax, ln_l + k, "-", dels[k], side, tv, False, del_bg)
            else:
                left = self._cell(syntax, 0, "", "", side, tv, True, None)
            if k < len(adds):
                right = self._cell(syntax, ln_r + k, "+", adds[k], side, tv, False, add_bg)
            else:
                right = self._cell(syntax, 0, "", "", side, tv, True, None)
            row = left + Text("   ") + right
            rows.append(DiffLine(row))
        return rows

    def _header(self) -> Static:
        tv = theme.palette(self)
        adds = sum(1 for k, _ in self.changes if k == "add")
        dels = sum(1 for k, _ in self.changes if k == "del")
        t = Text()
        t.append(self.filename, style=f"bold {tv['primary']}")
        t.append(f"   +{adds}", style=tv["success"])
        t.append(f"  -{dels}", style=tv["error"])
        return Static(t, classes="diff-header")

    def compose(self) -> ComposeResult:
        if self.show_header:
            yield self._header()
        layout = self._effective_layout()
        self._built_layout = layout
        rows = self._build_side() if layout == "side" else self._build_lines()
        truncatable = self.max_lines is not None and len(rows) > self.max_lines
        if truncatable and not self._expanded:
            yield from rows[: self.max_lines]
            yield ShowMore(hidden=len(rows) - self.max_lines)
        else:
            yield from rows
            if truncatable:  # expanded → offer collapse
                yield ShowMore(expanded=True)

    async def on_show_more_pressed(self, msg: ShowMore.Pressed) -> None:
        msg.stop()
        self._expanded = not self._expanded  # toggle expand / collapse
        await self.remove_children()
        await self.mount_all(self.compose())
        self.refresh(layout=True)  # re-measure so a collapse reclaims space

    async def on_resize(self) -> None:
        """Re-render only when the width crosses the side↔unified breakpoint."""
        if self._built_layout is not None and self._effective_layout() != self._built_layout:
            await self.remove_children()
            await self.mount_all(self.compose())
            self.refresh(layout=True)

    async def restyle(self) -> None:
        """Rebuild rows so baked-in line colors follow a palette switch."""
        await self.remove_children()
        await self.mount_all(self.compose())

