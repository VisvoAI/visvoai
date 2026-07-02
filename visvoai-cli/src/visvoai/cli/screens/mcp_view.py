"""MCPScreen — full-screen MCP server status + trust approval.

Infrastructure state (server connections, tool counts, setup help) lives here,
NOT in the conversation log — same separation as /model's ModelScreen. Rows are
navigable; enter on an untrusted project server marks it for trust. `dismiss()`
returns the list of server names the user chose to trust (empty = none).

This screen doubles as MCP onboarding: the empty state teaches all three setup
paths self-serve, and connected rows preview real tool names so a first-time
user immediately sees what the agent just gained.
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

# domain state → shared lifecycle state (iconography.STATE_STYLE)
_LIFECYCLE = {"connected": "ok", "failed": "failed",
              "untrusted": "attention", "disabled": "disabled"}
_STATE_LABEL = {"connected": "connected", "failed": "failed",
                "untrusted": "needs approval", "disabled": "disabled"}


class ServerRow(Vertical):
    """One server, three lines:
        ● name                    connected · global · stdio
          13 tools: echo, get-env, take-screenshot, …
          npx -y @modelcontextprotocol/server-everything
    """

    can_focus = False

    DEFAULT_CSS = """
    ServerRow { height: auto; padding: 0 1; margin: 0 0 1 0; }
    ServerRow:hover { background: $hover; }
    ServerRow.active { background: $hover; }
    ServerRow > .sr-head { height: 1; text-overflow: ellipsis; }
    ServerRow > .sr-tools { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
    ServerRow > .sr-target { height: 1; padding: 0 0 0 5; text-overflow: ellipsis; }
    """

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self, index: int, status, spec, tool_names: list[str],
                 pending_trust: bool = False) -> None:
        super().__init__()
        self.index = index
        self.status = status
        self.spec = spec
        self.tool_names = tool_names
        self.pending_trust = pending_trust
        self._active = False

    def compose(self) -> ComposeResult:
        yield Static(classes="sr-head")
        yield Static(classes="sr-tools")
        yield Static(classes="sr-target")

    def on_mount(self) -> None:
        self._render_row()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_class(active, "active")
        self._render_row()

    def set_pending(self, pending: bool) -> None:
        self.pending_trust = pending
        self._render_row()

    def _target(self) -> str:
        if self.spec is None:
            return ""
        if self.spec.command:
            return " ".join([self.spec.command, *self.spec.args])
        return self.spec.url or ""

    def _render_row(self) -> None:
        tv = theme.palette(self)
        s = self.status
        icon, token = STATE_STYLE[_LIFECYCLE[s.state]]
        state_style = f"dim {tv['muted']}" if token == "muted" else tv[token]

        # Line 1 — marker, state dot, name, then state · source · transport.
        head = Text()
        head.append(" ❯ " if self._active else "   ",
                    style=tv["primary"] if self._active else "dim")
        head.append(f"{icon} ", style=state_style)
        head.append(s.name, style=f"bold {tv['primary']}" if self._active
                    else f"bold {tv['foreground']}")
        label = "trusted — connects on close" if self.pending_trust else _STATE_LABEL[s.state]
        head.append(f"   {label}",
                    style=state_style if not self.pending_trust else tv["success"])
        head.append(f" · {s.source} · {s.transport}", style=f"dim {tv['muted']}")
        self.query_one(".sr-head", Static).update(head)

        # Line 2 — the payoff line: what the agent can now do / what's wrong.
        line2 = Text()
        if s.state == "connected":
            names = [n.split("__", 1)[-1] for n in self.tool_names]
            sample = ", ".join(names[:4]) + (", …" if len(names) > 4 else "")
            line2.append(f"{s.tool_count} tool{'s' if s.tool_count != 1 else ''}",
                         style=f"bold {tv['foreground']}")
            if sample:
                line2.append(f": {sample}", style=f"dim {tv['muted']}")
        elif s.state == "failed":
            line2.append(s.error or "connection failed", style=tv["error"])
        elif s.state == "untrusted":
            line2.append("this project's config defines it — press enter to trust "
                         "(one-time, remembered outside the repo)", style=tv["warning"])
        else:
            line2.append("disabled in config (enabled = false)", style=f"dim {tv['muted']}")
        self.query_one(".sr-tools", Static).update(line2)

        # Line 3 — what it runs / where it connects.
        target = self._target()
        self.query_one(".sr-target", Static).update(
            Text(target, style=f"dim {tv['muted']}") if target else Text(""))

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))


class MCPScreen(BlendScreen):
    """Full-screen MCP status view. `dismiss(list[str])` — names to trust."""

    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = CHROME_CSS + """
    MCPScreen { align: center top; }
    #mcp-add { padding: 0 1; margin: 1 0 0 0; }
    """

    def __init__(self, statuses: list, specs: dict,
                 tools_by_server: dict[str, list[str]] | None = None) -> None:
        super().__init__()
        # Untrusted first (actionable), then failed (needs attention), then the rest.
        order = {"untrusted": 0, "failed": 1, "connected": 2, "disabled": 3}
        self.statuses = sorted(statuses, key=lambda s: (order[s.state], s.name))
        self.specs = specs
        self.tools_by_server = tools_by_server or {}
        self.idx = 0
        self._to_trust: set[str] = set()

    def _summary(self) -> str:
        connected = [s for s in self.statuses if s.state == "connected"]
        n_tools = sum(s.tool_count for s in connected)
        parts = [f"{len(connected)} of {len(self.statuses)} server"
                 f"{'s' if len(self.statuses) != 1 else ''} connected"]
        if n_tools:
            parts.append(f"{n_tools} tools available to the agent")
        pending = sum(1 for s in self.statuses if s.state == "untrusted")
        if pending:
            parts.append(f"{pending} awaiting your approval")
        return "  ·  ".join(parts)

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp-box", classes="sc-box"):
            yield Static("MCP servers — plug external tools into the agent", id="mcp-title", classes="sc-title")
            yield Static(self._summary() if self.statuses else
                         "Connect the agent to browsers, issue trackers, databases and "
                         "hundreds of other tools via the Model Context Protocol.",
                         id="mcp-sub", classes="sc-sub")
            with VerticalScroll(id="mcp-list", classes="sc-list"):
                if self.statuses:
                    for i, s in enumerate(self.statuses):
                        yield ServerRow(i, s, self.specs.get(s.name),
                                        self.tools_by_server.get(s.name, []))
                else:
                    yield Static(self._empty_help(), id="mcp-empty", classes="sc-empty")
            if self.statuses:
                yield Static(self._add_more_help(), id="mcp-add")
            hint_line = (hint(("↑/↓", "navigate"),
                               ("enter", "trust/untrust a project server"),
                               ("esc", "apply & close"))
                         if self.statuses else
                         hint(("esc", "close — re-open /mcp after adding a server")))
            yield Static(hint_line, id="mcp-hint", classes="sc-hint")

    def _empty_help(self) -> Text:
        tv = theme.palette(self)
        cmd = tv["primary"]
        dim = f"dim {tv['muted']}"
        t = Text()

        def line(s: str = "", style: str = "") -> None:
            t.append(s + "\n", style=style)

        line("No servers yet — three ways to add one:", f"bold {tv['foreground']}")
        line()
        line("1  Command line (fastest)", f"bold {tv['foreground']}")
        line("   visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest", cmd)
        line("   visvoai mcp add linear --url https://mcp.linear.app/mcp \\", cmd)
        line("       --header 'Authorization=Bearer ${LINEAR_API_KEY}'", cmd)
        line()
        line("2  Edit config directly", f"bold {tv['foreground']}")
        line("   ~/.visvoai/config.toml (just you) or .visvoai/config.toml (this repo):", dim)
        line("   [mcp_servers.github]", cmd)
        line('   command = "npx"', cmd)
        line('   args = ["-y", "@modelcontextprotocol/server-github"]', cmd)
        line('   env = { GITHUB_PERSONAL_ACCESS_TOKEN = "${GITHUB_TOKEN}" }', cmd)
        line()
        line("3  Ask the agent", f"bold {tv['foreground']}")
        line('   Type: "add the GitHub MCP server to this project" — it writes the '
             "config for you.", dim)
        line()
        line("Secrets stay safe: always ${VAR} references — never paste raw tokens. "
             "Set the variable via /login, .visvoai/secrets.toml, or your shell.", dim)
        return t

    def _add_more_help(self) -> Text:
        tv = theme.palette(self)
        t = Text()
        t.append("Add more:  ", style=f"bold {tv['foreground']}")
        t.append("visvoai mcp add <name> -- <command …>", style=tv["primary"])
        t.append("  ·  ", style=f"dim {tv['muted']}")
        t.append("visvoai mcp add <name> --url <url>", style=tv["primary"])
        t.append("  ·  or just ask the agent to add one. Secrets: ${VAR} references, "
                 "never raw tokens.", style=f"dim {tv['muted']}")
        return t

    def on_mount(self) -> None:
        super().on_mount()
        self._sync()

    def _rows(self) -> list[ServerRow]:
        return list(self.query(ServerRow))

    def _sync(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_active(i == self.idx)
        if rows and 0 <= self.idx < len(rows):
            rows[self.idx].scroll_visible(animate=False)

    def on_key(self, event) -> None:
        if not self.statuses:
            return
        if event.key == "up":
            self.idx = (self.idx - 1) % len(self.statuses); self._sync(); event.stop()
        elif event.key == "down":
            self.idx = (self.idx + 1) % len(self.statuses); self._sync(); event.stop()
        elif event.key == "enter":
            self._toggle_trust(self.idx); event.stop()

    def on_server_row_chosen(self, msg: ServerRow.Chosen) -> None:
        self.idx = msg.index
        self._sync()
        self._toggle_trust(msg.index)

    def _toggle_trust(self, index: int) -> None:
        row = self._rows()[index]
        if row.status.state != "untrusted":
            return
        name = row.status.name
        if name in self._to_trust:
            self._to_trust.discard(name)
            row.set_pending(False)
        else:
            self._to_trust.add(name)
            row.set_pending(True)

    def action_close(self) -> None:
        self.dismiss(sorted(self._to_trust))
