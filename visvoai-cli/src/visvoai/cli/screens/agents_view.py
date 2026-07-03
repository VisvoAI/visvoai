"""AgentsScreen — full-screen agent roster + project-agent trust approval.

Shows the merged roster (built-ins + global + project agents) with each agent's
capability tier and model. Enter on an untrusted project agent marks it for
trust — same one-time approval model as project MCP servers. `dismiss()`
returns the agent names the user chose to trust (empty = none).

Doubles as onboarding: the footer teaches all three creation paths (CLI wizard,
definition file, asking the agent itself).
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

_TIER_LABEL = {"read-only": "read-only tools", "full": "full tools (edits gated)"}


class AgentRow(Vertical):
    """One agent, two lines:
        ● explore                 built-in · read-only tools · session model
          Fast read-only codebase/docs reconnaissance. ...
    """

    can_focus = False

    DEFAULT_CSS = """
    AgentRow { height: auto; padding: 0 1; margin: 0 0 1 0; }
    AgentRow:hover { background: $hover; }
    AgentRow.active { background: $hover; }
    AgentRow > .ar-head { height: 1; text-overflow: ellipsis; }
    AgentRow > .ar-desc { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
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
        yield Static(classes="ar-head")
        yield Static(classes="ar-desc")

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
        tier = _TIER_LABEL.get(s.tools.strip().lower(), f"tools: {s.tools}")
        head.append(f" · {s.source} · {tier} · {s.model or 'session model'}",
                    style=f"dim {tv['muted']}")
        self.query_one(".ar-head", Static).update(head)

        desc = Text()
        if not self.trusted and not self.pending_trust:
            desc.append("this project's files define it — press enter to trust "
                        "(one-time, remembered outside the repo)", style=tv["warning"])
        else:
            desc.append(s.description, style=f"dim {tv['muted']}")
        self.query_one(".ar-desc", Static).update(desc)

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class AgentsScreen(BlendScreen):
    """Full-screen agent roster. `dismiss(list[str])` — names to trust."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    AgentsScreen { align: center top; }
    #ag-add { padding: 0 1; margin: 1 0 0 0; }
    """

    def __init__(self, specs: list, trusted: dict[str, bool]) -> None:
        super().__init__()
        # Untrusted first (actionable), then built-ins, then customs by name.
        src_order = {"builtin": 0, "global": 1, "project": 2}
        self.specs = sorted(
            specs, key=lambda s: (trusted.get(s.name, True), src_order[s.source], s.name))
        self.trusted = trusted
        self.idx = 0
        self._to_trust: set[str] = set()

    def _summary(self) -> str:
        n = len(self.specs)
        custom = sum(1 for s in self.specs if s.source != "builtin")
        parts = [f"{n} agent{'s' if n != 1 else ''} available to delegate to"]
        if custom:
            parts.append(f"{custom} user-defined")
        pending = sum(1 for s in self.specs if not self.trusted.get(s.name, True))
        if pending:
            parts.append(f"{pending} awaiting your approval")
        return "  ·  ".join(parts)

    def compose(self) -> ComposeResult:
        with Vertical(id="ag-box", classes="sc-box"):
            yield Static("Agents — specialists the AI can delegate tasks to",
                         id="ag-title", classes="sc-title")
            yield Static(self._summary(), id="ag-sub", classes="sc-sub")
            with VerticalScroll(id="ag-list", classes="sc-list"):
                for i, s in enumerate(self.specs):
                    yield AgentRow(i, s, self.trusted.get(s.name, True))
            yield Static(self._add_more_help(), id="ag-add")
            yield Static(hint(("↑/↓", "navigate"),
                              ("enter/click", "trust/untrust a project agent"),
                              ("esc", "apply & close")),
                         id="ag-hint", classes="sc-hint")

    def _add_more_help(self) -> Text:
        tv = theme.palette(self)
        t = Text()
        t.append("Add your own:  ", style=f"bold {tv['foreground']}")
        t.append("visvoai agents create <name>", style=tv["primary"])
        t.append("  ·  drop a markdown file in ~/.visvoai/agents/",
                 style=f"dim {tv['muted']}")
        t.append("  ·  or just ask the agent to create one.",
                 style=f"dim {tv['muted']}")
        return t

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[AgentRow]:
        return list(self.query(AgentRow))

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

    def on_agent_row_chosen(self, msg: AgentRow.Chosen) -> None:
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
