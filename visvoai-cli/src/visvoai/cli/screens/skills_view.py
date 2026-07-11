"""SkillsScreen — skill roster + project-skill trust approval.

Same pattern as AgentsScreen/MCPScreen: rows navigable, enter on an untrusted
project skill marks it for trust, `dismiss(list[str])` returns names to trust.
A skill is instructions (knowledge), not capability — the trust gate exists
because a repo-controlled body still steers this machine's gated tools.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from visvoai.cli import theme
from visvoai.cli.iconography import STATE_STYLE
from visvoai.cli.screens.base import BlendScreen
from visvoai.cli.screens.chrome import CHROME_CSS, hint


class SkillRow(Vertical):
    """One skill, two lines: state + name + source/args/resources, then the
    description (or the trust prompt)."""

    can_focus = False

    DEFAULT_CSS = """
    SkillRow { height: auto; padding: 0 1; margin: 0 0 1 0; }
    SkillRow:hover { background: $hover; }
    SkillRow.active { background: $hover; }
    SkillRow > .sk-head { height: 1; text-overflow: ellipsis; }
    SkillRow > .sk-desc { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, spec, trusted: bool,
                 pending_trust: bool = False) -> None:
        super().__init__()
        self.index = index
        self.spec = spec
        self.trusted = trusted
        self.pending_trust = pending_trust
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="sk-head")
        yield Static(classes="sk-desc")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def set_pending(self, pending: bool) -> None:
        self.pending_trust = pending
        self._render_row()

    def _render_row(self) -> None:
        tv = theme.palette(self)
        s = self.spec
        state = "ok" if self.trusted else "attention"
        icon, token = STATE_STYLE[state]
        state_style = f"dim {tv['muted']}" if token == "muted" else tv[token]

        head = Text()
        head.append(" ❯ " if self._active else "   ",
                    style=tv["primary"] if self._active else "dim")
        head.append(f"{icon} ", style=state_style)
        head.append(s.name, style=f"bold {tv['primary']}" if self._active
                    else f"bold {tv['foreground']}")
        if self.pending_trust:
            head.append("   trusted — active on close", style=tv["success"])
        elif not self.trusted:
            head.append("   needs approval", style=tv["warning"])
        extras = [s.source]
        if s.args:
            extras.append("args: " + ", ".join(f"${a}" for a in s.args))
        n_res = len(s.resource_names())
        if n_res:
            extras.append(f"{n_res} resource file{'s' if n_res != 1 else ''}")
        head.append(" · " + " · ".join(extras), style=f"dim {tv['muted']}")
        self.query_one(".sk-head", Static).update(head)

        desc = Text()
        if not self.trusted and not self.pending_trust:
            desc.append("this project's files define it — press enter to trust "
                        "(one-time, remembered outside the repo)", style=tv["warning"])
        else:
            desc.append(s.description, style=f"dim {tv['muted']}")
        self.query_one(".sk-desc", Static).update(desc)

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class SkillsScreen(BlendScreen):
    """Full-screen skill roster. `dismiss(list[str])` — names to trust."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    SkillsScreen { align: center top; }
    #sk-add { padding: 0 1; margin: 1 0 0 0; }
    """

    def __init__(self, specs: list, trusted: dict[str, bool]) -> None:
        super().__init__()
        src_order = {"global": 0, "project": 1}
        self.specs = sorted(
            specs, key=lambda s: (trusted.get(s.name, True), src_order[s.source], s.name))
        self.trusted = trusted
        self.idx = 0
        self._to_trust: set[str] = set()

    def _summary(self) -> str:
        n = len(self.specs)
        parts = [f"{n} skill{'s' if n != 1 else ''} the AI can load on demand"]
        pending = sum(1 for s in self.specs if not self.trusted.get(s.name, True))
        if pending:
            parts.append(f"{pending} awaiting your approval")
        return "  ·  ".join(parts)

    def compose(self) -> ComposeResult:
        with Vertical(id="sk-box", classes="sc-box"):
            yield Static("Skills — reusable workflows the AI follows on demand",
                         id="sk-title", classes="sc-title")
            yield Static(self._summary() if self.specs else
                         "Teach the AI a repeatable workflow once — it loads the "
                         "instructions whenever a request matches.",
                         id="sk-sub", classes="sc-sub")
            with VerticalScroll(id="sk-list", classes="sc-list"):
                if self.specs:
                    for i, s in enumerate(self.specs):
                        yield SkillRow(i, s, self.trusted.get(s.name, True))
                else:
                    yield Static(self._empty_help(), id="sk-empty", classes="sc-empty")
            if self.specs:
                yield Static(self._add_more_help(), id="sk-add")
            yield Static(hint(("↑/↓", "navigate"),
                              ("enter/click", "trust/untrust a project skill"),
                              ("esc", "apply & close")),
                         id="sk-hint", classes="sc-hint")

    def _empty_help(self) -> Text:
        tv = theme.palette(self)
        cmd = tv["primary"]
        dim = f"dim {tv['muted']}"
        t = Text()

        def line(s: str = "", style: str = "") -> None:
            t.append(s + "\n", style=style)

        line("No skills yet — three ways to add one:", f"bold {tv['foreground']}")
        line()
        line("1  Command line", f"bold {tv['foreground']}")
        line("   visvoai skills create release-notes", cmd)
        line()
        line("2  Write the file directly", f"bold {tv['foreground']}")
        line("   ~/.visvoai/skills/<name>/SKILL.md (just you) or", dim)
        line("   .visvoai/skills/<name>/SKILL.md (this repo, shareable):", dim)
        line("   ---", cmd)
        line("   description: Draft release notes from the git log", cmd)
        line("   args:", cmd)
        line("     version: The version being released", cmd)
        line("   ---", cmd)
        line("   1. Run `git log <last-tag>..HEAD --oneline` …", cmd)
        line()
        line("3  Ask the agent", f"bold {tv['foreground']}")
        line('   Type: "create a skill for our release-notes process" — it '
             "writes the file for you.", dim)
        return t

    def _add_more_help(self) -> Text:
        tv = theme.palette(self)
        t = Text()
        t.append("Add more:  ", style=f"bold {tv['foreground']}")
        t.append("visvoai skills create <name>", style=tv["primary"])
        t.append("  ·  drop a SKILL.md under ~/.visvoai/skills/<name>/",
                 style=f"dim {tv['muted']}")
        t.append("  ·  or ask the agent to create one.", style=f"dim {tv['muted']}")
        return t

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[SkillRow]:
        return list(self.query(SkillRow))

    def _sync(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_active(i == self.idx)
        if rows and 0 <= self.idx < len(rows):
            rows[self.idx].scroll_visible(animate=False)

    def on_key(self, event) -> None:
        if not self.specs:
            return
        if event.key == "up":
            self.idx = (self.idx - 1) % len(self.specs); self._sync(); event.stop()
        elif event.key == "down":
            self.idx = (self.idx + 1) % len(self.specs); self._sync(); event.stop()
        elif event.key == "enter":
            self._toggle_trust(self.idx); event.stop()

    def on_skill_row_chosen(self, msg: SkillRow.Chosen) -> None:
        self.idx = msg.index
        self._sync()
        self._toggle_trust(msg.index)

    def _toggle_trust(self, index: int) -> None:
        row = self._rows()[index]
        if row.trusted:
            return
        name = row.spec.name
        if name in self._to_trust:
            self._to_trust.discard(name)
            row.set_pending(False)
        else:
            self._to_trust.add(name)
            row.set_pending(True)

    def action_close(self) -> None:
        self.dismiss(sorted(self._to_trust))
