"""GitScreen — a rich, full-screen git view for the opt-in commit flow.

Lays out the working tree the way a focused commit UI should: a diffstat summary,
staged / unstaged sections, colored status chips, per-file +/- counts with a
proportional diffstat bar, a single-line Summary field and an optional multi-line
Description (git's subject + body, sent as two `-m` parts). `ctrl+s` stages/unstages
the file under review, `enter` commits the staged index, `Ctrl+J` adds a newline in
the description, `esc` cancels. The CLI never auto-commits — this screen is the
explicit, reviewable gate.

Layout is adaptive and split at the top level: the whole commit window (details,
file list, message fields) sits alone on the left until a file is picked, then the
selected file's diff opens as a second column on the right.

Real git lives in `gitio`: with `cwd` set, staging and commit hit the repo (and the
status is read by `gitio.working_tree_status`); with `cwd=None` (tests, `/demo`) the
screen runs on an in-memory status dict and commit just returns the message.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Static, TextArea

from visvoai.cli import theme
from visvoai.cli.screens.base import BlendScreen
from visvoai.cli.widgets.diff import CleanDiff

# status letter -> palette key for its accent (chip + path emphasis)
_STATE_COLORS = {"M": "warning", "A": "success", "D": "error"}


class GitFileRow(Horizontal):
    """One changed file in aligned columns:
    `chip | path | +adds | -dels | diffstat-bar`. Fixed-width count/bar columns
    keep everything aligned across rows of any path length."""

    BAR_CELLS = 8

    DEFAULT_CSS = """
    GitFileRow { height: 1; padding: 0 1; }
    GitFileRow:hover { background: $hover; }
    /* The file currently under review (its diff is in the preview pane). */
    GitFileRow.current { background: $hover; }
    GitFileRow > .gf-stage { width: 2; }
    GitFileRow > .gf-chip { width: 4; }
    GitFileRow > .gf-path { width: 1fr; text-overflow: ellipsis; }
    GitFileRow > .gf-adds { width: 6; content-align: right middle; }
    GitFileRow > .gf-dels { width: 6; content-align: right middle; }
    GitFileRow > .gf-bar { width: 10; content-align: right middle; padding: 0 0 0 1; }
    """

    class Selected(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, file: dict, max_total: int, index: int = 0) -> None:
        super().__init__()
        self.file = file
        self.max_total = max_total
        self.index = index

    def on_click(self) -> None:
        self.post_message(self.Selected(self.index))

    def compose(self) -> ComposeResult:
        yield Static(classes="gf-stage")
        yield Static(classes="gf-chip")
        yield Static(classes="gf-path")
        yield Static(classes="gf-adds")
        yield Static(classes="gf-dels")
        yield Static(classes="gf-bar")

    def on_mount(self) -> None:
        tv = theme.palette(self)
        f = self.file
        color = tv[_STATE_COLORS.get(f["state"], "muted")]
        # stage marker: filled when staged, hollow when not (ctrl+s toggles)
        self.query_one(".gf-stage", Static).update(
            Text("✓" if f["staged"] else "·",
                 style=tv["success"] if f["staged"] else f"dim {tv['muted']}"))
        # chip: a colored block with the status letter knocked out (reverse)
        self.query_one(".gf-chip", Static).update(
            Text(f" {f['state']} ", style=f"bold {color} reverse"))
        self.query_one(".gf-path", Static).update(
            Text(f["path"], style=f"bold {tv['foreground']}" if f["staged"] else tv["muted"]))
        self.query_one(".gf-adds", Static).update(
            Text(f"+{f['adds']}" if f["adds"] else "·", style=tv["success"] if f["adds"] else f"dim {tv['muted']}"))
        self.query_one(".gf-dels", Static).update(
            Text(f"-{f['dels']}" if f["dels"] else "·", style=tv["error"] if f["dels"] else f"dim {tv['muted']}"))
        self.query_one(".gf-bar", Static).update(self._bar(tv, f["adds"], f["dels"]))

    def _bar(self, tv: dict, adds: int, dels: int) -> Text:
        total = adds + dels
        if total == 0 or self.max_total == 0:
            return Text("")
        length = max(1, round(total / self.max_total * self.BAR_CELLS))
        greens = round(adds / total * length)
        reds = length - greens
        t = Text()
        t.append("▰" * greens, style=tv["success"])
        t.append("▰" * reds, style=tv["error"])
        t.append("▱" * (self.BAR_CELLS - length), style=f"dim {tv['muted']}")
        return t


class CommitMessageArea(TextArea):
    """Multi-line commit message. `enter` commits, `Ctrl+J`/`Opt+Enter` newline —
    same key idiom as the app's other inline editors."""

    class Commit(Message):
        pass

    def __init__(self, default: str) -> None:
        super().__init__(text=default, soft_wrap=True, id="git-message")

    async def _on_key(self, event) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.Commit())
            return
        if event.key in ("ctrl+j", "alt+enter", "shift+enter"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        await super()._on_key(event)


class GitScreen(BlendScreen):
    """Full-screen commit view. `dismiss(message | None)`."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        # Review the change one file at a time. ctrl+up/down so they don't collide
        # with typing in the commit-message editor (which owns plain up/down/j/k).
        Binding("ctrl+down", "next_file", "Next file", show=False),
        Binding("ctrl+up", "prev_file", "Prev file", show=False),
        # Stage / unstage the file under review. ctrl+s so it fires while the
        # message editor (which owns plain space) holds focus.
        Binding("ctrl+s", "toggle_stage", "Stage/unstage", show=False),
    ]

    DEFAULT_CSS = """
    GitScreen { align: center top; }
    /* Whole screen is two top-level columns: the full commit window on the left,
       the selected file's diff on the right. The right column is hidden until a
       file is picked (display:none → no space), so the left window sits centered
       and alone until then; selecting a file opens the diff beside it. */
    GitScreen > #git-screen { width: 100%; height: 1fr; align: center top; }
    /* 50 / 50 when split; the box spans full width while the diff column is hidden. */
    #git-box { width: 1fr; padding: 1 3; height: 1fr; }
    #git-preview-col { width: 1fr; height: 1fr; padding: 1 2; display: none; scrollbar-size-vertical: 1; }
    #git-preview { height: auto; }

    #git-title { text-style: bold; color: $primary; padding: 0 1; }
    #git-branch { padding: 0 1; margin: 1 0 0 0; }
    #git-stat { padding: 0 1; margin: 0 0 1 0; }

    .git-section {
        text-style: bold; padding: 0 1; margin: 1 0 0 0;
        border-bottom: solid $primary-darken-2;
    }
    .git-section-staged { color: $success; }
    .git-section-unstaged { color: $warning; }

    #git-review-hint { color: $muted; padding: 0 1; margin: 1 0 0 0; }
    #git-files { height: 1fr; scrollbar-size-vertical: 1; }
    .git-preview-empty { color: $muted; padding: 0 1; }

    #git-summary-label, #git-msg-label {
        text-style: bold; color: $primary; padding: 0 1; margin: 1 0 0 0;
    }
    #git-subject, #git-subject:focus {
        border: none; background: $panel; border-left: solid $primary;
        padding: 0 1; margin: 0 0 1 0;
    }
    #git-message, #git-message:focus {
        height: auto; max-height: 6; border: none; background: $panel;
        border-left: solid $primary-darken-2; padding: 0 1; margin: 0 0 1 0;
    }
    #git-hint { padding: 0 1; }
    """

    def __init__(self, status: dict, cwd: str | None = None) -> None:
        super().__init__()
        self.status = status
        # cwd set → real repo: staging/commit hit git via gitio. None → mock/demo
        # mode (tests, /demo): staging is in-memory, commit just returns the message.
        self._cwd = cwd
        # Flat review order = staged then unstaged, matching the composed rows.
        self._files_flat: list[dict] = self._staged() + self._unstaged()
        # No file under review until the user picks one (click / ctrl+↑↓) — the
        # preview stays empty on open so the screen reads as a plain change list.
        self._current = -1

    # ── derived views over the mock status ────────────────────────────────────
    def _staged(self) -> list[dict]:
        return [f for f in self.status["files"] if f["staged"]]

    def _unstaged(self) -> list[dict]:
        return [f for f in self.status["files"] if not f["staged"]]

    def _max_total(self) -> int:
        return max((f["adds"] + f["dels"] for f in self.status["files"]), default=0)

    def _branch_line(self) -> Text:
        tv = self.app.theme_variables
        t = Text()
        t.append("⎇  ", style=tv["primary"])
        t.append(self.status["branch"], style=f"bold {tv['foreground']}")
        upstream = self.status.get("upstream")
        ahead = self.status.get("ahead")
        behind = self.status.get("behind")
        if upstream:
            bits = []
            if ahead:
                bits.append(f"↑{ahead}")
            if behind:
                bits.append(f"↓{behind}")
            sync = " ".join(bits) if bits else "up to date"
            t.append(f"   {sync} · ", style=f"dim {tv['muted']}")
            t.append(upstream, style=tv["muted"])
        return t

    def _stat_line(self) -> Text:
        tv = self.app.theme_variables
        files = self.status["files"]
        adds = sum(f["adds"] for f in files)
        dels = sum(f["dels"] for f in files)
        n = len({f["path"] for f in files})  # distinct paths (a file may have staged + unstaged rows)
        t = Text()
        t.append(f"{n} file{'s' if n != 1 else ''} changed", style=tv["foreground"])
        t.append(f"   +{adds}", style=f"bold {tv['success']}")
        t.append(f"  -{dels}", style=f"bold {tv['error']}")
        return t

    def _section(self, label: str, count: int, staged: bool) -> Static:
        cls = "git-section-staged" if staged else "git-section-unstaged"
        return Static(f"{label} ({count})", classes=f"git-section {cls}")

    def _file_widgets(self) -> list:
        """Section headers + file rows in review order (staged then unstaged).
        Recomputes `_files_flat` so it always matches the mounted rows — shared by
        the initial compose and the post-staging rebuild."""
        max_total = self._max_total()
        staged, unstaged = self._staged(), self._unstaged()
        self._files_flat = staged + unstaged
        widgets: list = []
        idx = 0
        if staged:
            widgets.append(self._section("Staged", len(staged), staged=True))
            for f in staged:
                widgets.append(GitFileRow(f, max_total, index=idx)); idx += 1
        if unstaged:
            widgets.append(self._section("Unstaged", len(unstaged), staged=False))
            for f in unstaged:
                widgets.append(GitFileRow(f, max_total, index=idx)); idx += 1
        return widgets

    def compose(self) -> ComposeResult:
        with Horizontal(id="git-screen"):
            with Vertical(id="git-box"):                       # left: the full commit window
                yield Static("Commit changes", id="git-title")
                yield Static(self._branch_line(), id="git-branch")
                yield Static(self._stat_line(), id="git-stat")
                yield Static("Review  ·  click a file (or ctrl+↑/↓) to view its diff  ·  ctrl+s stage/unstage",
                             id="git-review-hint")
                with VerticalScroll(id="git-files"):
                    yield from self._file_widgets()
                yield Static("Summary", id="git-summary-label")
                yield Input(value=self.status.get("suggested_message", ""),
                            placeholder="One-line summary (required)", id="git-subject")
                yield Static("Description (optional)", id="git-msg-label")
                yield CommitMessageArea("")
                yield Static(self._hint(), id="git-hint")
            with VerticalScroll(id="git-preview-col"):         # right: only the diff
                yield Vertical(id="git-preview")

    def _hint(self) -> Text:
        tv = self.app.theme_variables
        t = Text()
        t.append("enter", style=f"bold {tv['secondary']}")
        t.append(" commit", style=tv["muted"])
        t.append("    ctrl+s", style=f"bold {tv['secondary']}")
        t.append(" stage", style=tv["muted"])
        t.append("    Ctrl+J", style=f"bold {tv['secondary']}")
        t.append(" newline", style=tv["muted"])
        t.append("    esc", style=f"bold {tv['secondary']}")
        t.append(" cancel", style=tv["muted"])
        return t

    def on_mount(self) -> None:
        super().on_mount()  # blend with the terminal background
        # No diff shown on open — the preview starts with its placeholder and is
        # only populated when the user picks a file.
        subject = self.query_one("#git-subject", Input)
        subject.focus()
        subject.cursor_position = len(subject.value)

    # ── aggregate file-by-file review ─────────────────────────────────────────
    def _rows(self) -> list[GitFileRow]:
        return list(self.query(GitFileRow))

    async def select_file(self, i: int) -> None:
        """Make file `i` the one under review: highlight its row, show its diff."""
        rows = self._rows()
        if not rows:
            return
        self._current = max(0, min(i, len(rows) - 1))
        for r in rows:
            r.set_class(r.index == self._current, "current")
        await self._show_preview(self._files_flat[self._current])
        # Open the right-hand diff column — a file is now under review (one → two cols).
        self.query_one("#git-preview-col").display = True

    async def _show_preview(self, file: dict) -> None:
        pane = self.query_one("#git-preview", Vertical)
        await pane.remove_children()  # await: avoid racing the next mount
        diff = file.get("diff")
        if diff:
            # show_header → the panel carries the file name + counts (no separate label).
            # Unified layout: the diff column is one narrow pane, not wide enough to pair.
            await pane.mount(CleanDiff(file["path"], diff, diff_layout="unified", show_header=True))
        else:
            await pane.mount(Static("no diff preview for this file",
                                    classes="git-preview-empty"))

    async def on_git_file_row_selected(self, msg: GitFileRow.Selected) -> None:
        msg.stop()
        await self.select_file(msg.index)

    async def action_next_file(self) -> None:
        await self.select_file(self._current + 1)

    async def action_prev_file(self) -> None:
        await self.select_file(self._current - 1)

    # ── staging ───────────────────────────────────────────────────────────────
    async def _rebuild_files(self, keep_path: str | None) -> None:
        """Re-mount the file list + dependent header lines after a staging change,
        keeping the same file under review when it survives."""
        files = self.query_one("#git-files", VerticalScroll)
        await files.remove_children()
        await files.mount(*self._file_widgets())
        self.query_one("#git-stat", Static).update(self._stat_line())
        self.query_one("#git-branch", Static).update(self._branch_line())
        target = 0
        if keep_path is not None:
            for i, f in enumerate(self._files_flat):
                if f["path"] == keep_path:
                    target = i
                    break
        await self.select_file(target)

    async def action_toggle_stage(self) -> None:
        """Stage / unstage the file under review (ctrl+s). Real repo → git via
        gitio (then re-read so partial-stage merges stay accurate); mock → flip
        the in-memory flag."""
        if not self._files_flat or self._current < 0:
            self.app.notify("pick a file first (click or ctrl+↑/↓), then ctrl+s")
            return
        f = self._files_flat[self._current]
        path, was_staged = f["path"], f["staged"]
        if self._cwd is not None:
            from visvoai.cli import gitio
            ok = (gitio.unstage if was_staged else gitio.stage)(self._cwd, path)
            if not ok:
                self.app.notify(f"git: could not {'unstage' if was_staged else 'stage'} {path}")
                return
            fresh = gitio.working_tree_status(self._cwd)
            self.status = fresh if fresh else {**self.status, "files": []}
        else:
            f["staged"] = not was_staged
        await self._rebuild_files(keep_path=path)

    # ── commit ────────────────────────────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "git-subject":
            event.stop()
            self.run_worker(self._commit())

    def on_commit_message_area_commit(self, event: CommitMessageArea.Commit) -> None:
        self.run_worker(self._commit())

    async def _commit(self) -> None:
        subject = self.query_one("#git-subject", Input).value.strip()
        body = self.query_one(CommitMessageArea).text.strip()
        if not subject:
            self.app.notify("commit summary required")
            return
        staged_paths = {f["path"] for f in self.status["files"] if f["staged"]}
        if not staged_paths:
            self.app.notify("nothing staged — ctrl+s to stage a file")
            return
        if self._cwd is not None:
            from visvoai.cli import gitio
            ok, detail = gitio.commit(self._cwd, subject, body)
            if not ok:
                self.app.notify(f"git commit failed: {detail or 'unknown error'}")
                return
        self.dismiss({"message": subject, "description": body,
                      "n_files": len(staged_paths), "branch": self.status["branch"]})

    def action_cancel(self) -> None:
        self.dismiss(None)
