"""
visvoai.cli.main — the `visvoai` entry point.

Two surfaces share one command:
  visvoai                       → launch the Textual TUI (interactive REPL)
  visvoai "refactor the auth"   → single-shot: stream one turn to stdout
  visvoai --cwd path "..."      → run against another working directory
  visvoai --model <id> ...      → pick a deployment (default = registry default)

The agent reads/edits files, runs shell commands, and searches the web.
"""
import asyncio
import os
import sys

import click


class _DefaultGroup(click.Group):
    """A click Group that falls back to a default command, so `visvoai <prompt>`
    and `visvoai --model x` keep working while `visvoai mcp …` dispatches to a
    subcommand. Anything whose first token isn't a known subcommand is routed to
    the default command untouched."""

    def __init__(self, *args, default_command: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._default = default_command

    # Group-level flags that must NOT be routed into the default command.
    _GROUP_FLAGS = ("--help", "-h", "--version")

    def parse_args(self, ctx, args):
        if not args or (args[0] not in self.commands
                        and args[0] not in self._GROUP_FLAGS):
            args = [self._default, *args]
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup, default_command="chat",
             context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="visvoai-cli", prog_name="visvoai-cli",
                      message="%(prog)s v%(version)s")
def cli() -> None:
    """VisvoAI — terminal coding agent.

    \b
    visvoai                       launch the interactive TUI
    visvoai "refactor the auth"   single-shot: stream one turn to stdout
    visvoai mcp add/list/remove   manage MCP servers

    Chat options (--model, --cwd, --resume, …): `visvoai chat --help`.
    """


@cli.command("chat")
@click.argument("prompt", nargs=-1, required=False)
@click.option(
    "--model",
    default=None,
    metavar="DEPLOYMENT_ID",
    help="Deployment id (e.g. gemini:gemini-3-flash-preview). Default: the "
         "registry's default chat model.",
)
@click.option(
    "--cwd",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    show_default=True,
    help="Working directory for file operations.",
)
@click.option(
    "--resume",
    is_flag=False,
    flag_value="__last__",
    default=None,
    metavar="ID",
    help="Resume a conversation by id (or the latest if no id). TUI only.",
)
@click.option("--verbose", is_flag=True, help="Single-shot: show tool inputs/outputs.")
@click.option("--yes", "-y", "assume_yes", is_flag=True,
              help="Single-shot: auto-approve mutating tools (edit/write/shell). Without "
                   "it, headless runs DENY mutations except those pre-authorized in "
                   "[permissions]. Path confinement applies either way.")
@click.option("--refresh-models", is_flag=True,
              help="Re-fetch the models.dev catalog (drops the cache), then exit.")
@click.option(
    "--set-key",
    "set_key_provider",
    default=None,
    metavar="PROVIDER",
    help="Store an API key for a provider (e.g. gemini), then exit. Prompts for the "
         "key (hidden) and where to save it (global or this project).",
)
def chat(prompt: tuple, model: str, cwd: str, resume: str, verbose: bool,
         assume_yes: bool, set_key_provider: str, refresh_models: bool) -> None:
    """VisvoAI — terminal coding agent. Run with no prompt for the interactive TUI,
    or pass a prompt for a single-shot stream."""
    abs_cwd = os.path.abspath(cwd)
    if set_key_provider:
        _set_key_flow(set_key_provider, abs_cwd)
        return
    if refresh_models:
        from visvoai.cli.catalog import install_cli_catalog
        n = install_cli_catalog(force_refresh=True)
        click.echo(f"Refreshed model catalog — {n} models." if n
                   else "Could not refresh (offline?) — using the baked floor.")
        return
    text = " ".join(prompt).strip()
    if text:
        asyncio.run(_run_single_shot(text, model, abs_cwd, verbose, assume_yes))
    else:
        _launch_tui(model, resume, abs_cwd)


def _bootstrap_env(cwd: str) -> None:
    """Make provider keys available before any model is built — for BOTH surfaces.
    Loads the nearest .env, then fills os.environ from the stored key layers
    (project secrets → global config) for anything not already set."""
    from dotenv import load_dotenv
    from visvoai.cli.catalog import install_cli_catalog
    from visvoai.cli.keys import load_keys_into_env

    load_dotenv()                  # .env → os.environ (counts as the env layer)
    load_keys_into_env(cwd)        # project/global stored keys fill the rest
    install_cli_catalog()          # baked + cached models.dev → the live picker catalog


def _set_key_flow(provider: str, cwd: str) -> None:
    """Headless `--set-key`: prompt (hidden) for the key + scope, store it. set_key
    re-reads the file after writing and raises OSError if the key didn't land —
    we surface that rather than printing "saved" against a broken file."""
    from visvoai.cli import keys

    key = click.prompt(f"{keys.env_var_for(provider)}", hide_input=True).strip()
    if not key:
        click.echo("No key entered — nothing saved.", err=True)
        return
    scope = click.prompt(
        "Save where? [g]lobal (~/.visvoai) or [p]roject (.visvoai, gitignored)",
        type=click.Choice(["g", "p"]), default="g", show_choices=False,
    )
    try:
        path = keys.set_key(provider, key, "global" if scope == "g" else "project", cwd)
    except OSError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)
    click.echo(f"Saved {provider} key to {path}")


def _launch_tui(model: str | None, resume: str | None, cwd: str) -> None:
    """Launch the Textual REPL. Resolves provider keys (env/.env/stored) so the TUI
    can chat without a manual export, and queries the terminal background BEFORE
    Textual grabs stdin so the app can paint that exact colour and blend in."""
    _bootstrap_env(cwd)
    os.chdir(cwd)

    from visvoai.cli import VisvoApp
    from visvoai.cli.termbg import detect_terminal_bg

    app = VisvoApp(term_bg=detect_terminal_bg(), model=model, resume=resume)
    app.run()
    # After the alt-screen tears down, drop a resume hint into normal scrollback —
    # only when a conversation actually happened (a turn was persisted).
    if app._conv_id:
        click.echo(
            f"\n  Conversation saved (id: {app._conv_id}).\n"
            f"  Resume it next time with  visvoai --resume  (or /resume in the TUI).\n"
        )


async def _run_single_shot(prompt: str, model: str | None, cwd: str, verbose: bool,
                           assume_yes: bool = False) -> None:
    """Stream one turn to stdout — no TUI. Builds the same CLIRuntime graph the TUI
    uses, through the public visvoai-ai resolver."""
    _bootstrap_env(cwd)            # same key resolution as the TUI (env/.env/stored)
    os.chdir(cwd)  # run_shell + file tools inherit this

    from visvoai.ai import build_chat_model, default_deployment
    from visvoai.cli.agent import SYSTEM_PROMPT

    deployment_id = model or default_deployment()
    if not deployment_id:
        click.echo("ERROR: no chat model available in the registry.", err=True)
        sys.exit(1)
    try:
        chat_model = build_chat_model(deployment_id)
    except (KeyError, ValueError, ImportError) as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    from langchain_core.messages import HumanMessage

    from visvoai.cli.context import build_assembler
    from visvoai.cli.runtime import CLIRuntime
    from visvoai.cli.tools import build_cli_tools

    if assume_yes:
        # Explicit opt-in: auto-approve mutations (still path-confined).
        tools = build_cli_tools(cwd=cwd)
    else:
        # No TTY to approve at: DENY mutations except those pre-authorized in
        # [permissions]. The agent gets a decline message and adapts/explains.
        from visvoai.cli.gated_tools import build_gated_tools
        from visvoai.cli.permissions import load_policy

        policy = load_policy(cwd)

        async def _headless_approve(tool_name: str, args: dict) -> bool:
            if policy.auto_allow(tool_name, args):
                return True
            click.echo(
                f"\n[blocked: {tool_name} needs approval — re-run with --yes, or "
                f"pre-authorize it in .visvoai/config.toml [permissions]]", err=True)
            return False

        tools = build_gated_tools(cwd=cwd, approve=_headless_approve)

    # MCP tools: discovered once, appended to the set. In gated mode they need
    # approval like shell (external actions); with --yes they run ungated.
    from visvoai.cli.mcp import get_mcp_tools
    mcp_statuses, mcp_tools = await get_mcp_tools(cwd)
    if verbose:
        for s in mcp_statuses:
            if s.state == "failed":
                click.echo(f"[mcp: {s.name} failed — {s.error}]", err=True)
            elif s.state == "untrusted":
                click.echo(f"[mcp: {s.name} is project-defined and untrusted — "
                           f"approve it via /mcp in the TUI first]", err=True)
    if mcp_tools:
        if assume_yes:
            tools += mcp_tools
        else:
            from visvoai.cli.gated_tools import gate_tool
            tools += [gate_tool(t, _headless_approve) for t in mcp_tools]

    # Background process tools — registry lives for this invocation only; every
    # spawned process is killed in the finally below (a one-shot run must not
    # leave servers behind).
    from visvoai.cli.processes import ProcessRegistry
    from visvoai.cli.tools.background import build_background_tools
    processes = ProcessRegistry()
    tools += build_background_tools(
        processes, cwd=cwd, approve=None if assume_yes else _headless_approve)

    assembler = build_assembler(SYSTEM_PROMPT, cwd)
    graph = CLIRuntime(assembler=assembler).build_graph(
        model=chat_model,
        core_tools=tools,
        all_tools_map={t.name: t for t in tools},
        system_prompt=SYSTEM_PROMPT,
    )
    state = {"messages": [HumanMessage(content=prompt)]}

    try:
        # Explicit recursion_limit — keeps a deep turn from crashing on LangGraph's
        # default 25 before the core graph's soft step cap can force a clean finalize.
        async for event in graph.astream_events(
            state, version="v2", config={"recursion_limit": 100}
        ):
            kind = event.get("event", "")
            # Subagent-graph events bubble into this stream (same leak the TUI
            # filters): print only a marker per tool step, never their text —
            # it would interleave with the main agent's answer.
            from visvoai.cli.agents import subagent_name_from_tags
            sub_name = subagent_name_from_tags(event.get("tags"))
            if sub_name is not None:
                if kind == "on_tool_start":
                    click.echo(f"\n[agent {sub_name}: {event.get('name', 'tool')}]",
                               err=True)
                continue
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and getattr(chunk, "content", None):
                    click.echo(chunk.content, nl=False)
            elif kind == "on_tool_start":
                name = event.get("name", "tool")
                if verbose:
                    click.echo(f"\n\n[tool: {name}] {event['data'].get('input', {})}", err=True)
                else:
                    click.echo(f"\n[{name}]", err=True)
            elif kind == "on_tool_end" and verbose:
                out = str(event["data"].get("output", ""))
                click.echo(f"  → {out[:200]}{'…' if len(out) > 200 else ''}", err=True)
    except KeyboardInterrupt:
        click.echo("\n[interrupted]", err=True)
    finally:
        processes.stop_all(by="shutdown")
        from visvoai.cli.mcp import close_mcp_sessions
        await close_mcp_sessions()

    click.echo()  # trailing newline after the streamed response




# ── `visvoai mcp …` — manage MCP servers ─────────────────────────────────────

def _kv_pairs(pairs: tuple, what: str, sep_colon_ok: bool = False) -> dict:
    """Parse repeated 'KEY=VALUE' (and for headers also 'Name: Value') options."""
    out = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
        elif sep_colon_ok and ":" in p:
            k, v = p.split(":", 1)
        else:
            raise click.UsageError(f"invalid {what} '{p}' — expected KEY=VALUE")
        out[k.strip()] = v.strip()
    return out


def _mcp_config_path(project: bool, cwd: str):
    from visvoai.cli.keys import global_config_path
    from visvoai.cli.store import project_root

    if not project:
        return global_config_path()
    return project_root(os.path.abspath(cwd)) / ".visvoai" / "config.toml"


@cli.group("mcp")
def mcp_group() -> None:
    """Manage MCP servers (Model Context Protocol).

    \b
    visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest
    visvoai mcp add linear --url https://mcp.linear.app/mcp \\
        --header 'Authorization=Bearer ${LINEAR_API_KEY}'
    visvoai mcp list
    visvoai mcp remove chrome

    Secrets: always pass ${VAR} references, never raw tokens — values expand
    from the environment (fed by the layered key store) at connect time.
    """


@mcp_group.command("add")
@click.argument("name")
@click.argument("command_args", nargs=-1)
@click.option("--url", default=None, help="Remote server URL (instead of a command).")
@click.option("--header", "headers", multiple=True,
              help="HTTP header for --url servers, KEY=VALUE (repeatable).")
@click.option("--env", "envs", multiple=True,
              help="Env var for command servers, KEY=VALUE (repeatable).")
@click.option("--project", is_flag=True,
              help="Write to this project's .visvoai/config.toml (shareable via the "
                   "repo; teammates approve it once) instead of ~/.visvoai.")
@click.option("--cwd", default=".", help="Project directory (with --project).")
def mcp_add(name: str, command_args: tuple, url: str, headers: tuple,
            envs: tuple, project: bool, cwd: str) -> None:
    """Add (or replace) an MCP server. For local servers put the launch command
    after `--`: visvoai mcp add github -- npx -y @modelcontextprotocol/server-github"""
    from visvoai.cli.mcp import upsert_server_config

    if bool(url) == bool(command_args):
        raise click.UsageError("give exactly one of: a command after `--`, or --url")
    if url and envs:
        raise click.UsageError("--env is for command servers; use --header with --url")
    if command_args and headers:
        raise click.UsageError("--header is for --url servers; use --env with a command")

    path = _mcp_config_path(project, cwd)
    try:
        if url:
            upsert_server_config(path, name, url=url,
                                 headers=_kv_pairs(headers, "header", sep_colon_ok=True))
        else:
            upsert_server_config(path, name, command=command_args[0],
                                 args=list(command_args[1:]),
                                 env=_kv_pairs(envs, "env"))
    except ValueError as e:
        raise click.UsageError(str(e))

    click.echo(f"Added MCP server '{name}' → {path}")
    for v in (*headers, *envs):
        if "${" not in v.split("=", 1)[-1] and any(
                s in v.lower() for s in ("token", "key", "authorization", "secret")):
            click.echo("  warning: that looks like a raw secret — prefer KEY='${VAR}' "
                       "and store the var via `visvoai --set-key` or secrets.toml.", err=True)
    if project:
        click.echo("  Project-defined server: the TUI will ask for one-time approval (/mcp).")
    click.echo("  Check it: visvoai mcp list   (status shows in the TUI via /mcp)")


@mcp_group.command("list")
@click.option("--cwd", default=".", help="Project directory to resolve config for.")
def mcp_list(cwd: str) -> None:
    """List configured MCP servers (no network — connection status lives in /mcp)."""
    from visvoai.cli.mcp import is_trusted, load_mcp_servers

    abs_cwd = os.path.abspath(cwd)
    servers = load_mcp_servers(abs_cwd)
    if not servers:
        click.echo("No MCP servers configured.\n"
                   "Add one:  visvoai mcp add <name> -- <command …>   |   "
                   "visvoai mcp add <name> --url <url>")
        return
    for s in sorted(servers.values(), key=lambda s: s.name):
        target = s.url or " ".join([s.command, *s.args])
        flags = []
        if not s.enabled:
            flags.append("disabled")
        if s.source == "project" and not is_trusted(abs_cwd, s):
            flags.append("awaiting approval (/mcp in the TUI)")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        click.echo(f"{s.name:<20} {s.source:<8} {s.transport:<16} {target}{suffix}")


@mcp_group.command("remove")
@click.argument("name")
@click.option("--cwd", default=".", help="Project directory to resolve config for.")
def mcp_remove(name: str, cwd: str) -> None:
    """Remove an MCP server from whichever config file(s) define it."""
    from visvoai.cli.mcp import remove_server_config

    removed = []
    for project in (False, True):
        try:
            path = _mcp_config_path(project, cwd)
        except Exception:
            continue
        if remove_server_config(path, name):
            removed.append(str(path))
    if removed:
        for p in removed:
            click.echo(f"Removed '{name}' from {p}")
    else:
        click.echo(f"No MCP server named '{name}' found.", err=True)
        sys.exit(1)


# ── `visvoai agents …` — manage subagents ────────────────────────────────────

def _agents_dir(project: bool, cwd: str):
    from visvoai.cli.agents import _agents_dir_global, _agents_dir_project
    return _agents_dir_project(os.path.abspath(cwd)) if project else _agents_dir_global()


@cli.group("agents")
def agents_group() -> None:
    """Manage agents (subagents the main agent can delegate tasks to).

    \b
    visvoai agents list                  merged roster (built-ins + yours)
    visvoai agents create reviewer       interactive: description, tools, model
    visvoai agents show reviewer         print a definition
    visvoai agents remove reviewer

    Built-ins (explore, general) always exist. Your agents are markdown files —
    ~/.visvoai/agents/<name>.md (global) or .visvoai/agents/<name>.md (project,
    shareable via the repo; teammates approve it once in /agents).
    """


@agents_group.command("list")
@click.option("--cwd", default=".", help="Project directory to resolve agents for.")
def agents_list(cwd: str) -> None:
    """List the merged agent roster."""
    from visvoai.cli.agents import is_trusted, load_agent_specs

    abs_cwd = os.path.abspath(cwd)
    for s in load_agent_specs(abs_cwd).values():
        flags = []
        if s.source == "project" and not is_trusted(abs_cwd, s):
            flags.append("awaiting approval (/agents in the TUI)")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        model = s.model or "session model"
        click.echo(f"{s.name:<16} {s.source:<8} {s.tools:<12} {model:<28} "
                   f"{s.description}{suffix}")


@agents_group.command("show")
@click.argument("name")
@click.option("--cwd", default=".", help="Project directory to resolve agents for.")
def agents_show(name: str, cwd: str) -> None:
    """Print an agent's full definition (system prompt included)."""
    from visvoai.cli.agents import load_agent_specs

    spec = load_agent_specs(os.path.abspath(cwd)).get(name)
    if spec is None:
        click.echo(f"No agent named '{name}'.", err=True)
        sys.exit(1)
    click.echo(f"name:        {spec.name}")
    click.echo(f"source:      {spec.source}" + (f"  ({spec.path})" if spec.path else ""))
    click.echo(f"description: {spec.description}")
    click.echo(f"tools:       {spec.tools}")
    click.echo(f"model:       {spec.model or 'session model'}")
    click.echo("\n--- system prompt ---")
    click.echo(spec.prompt)


@agents_group.command("create")
@click.argument("name")
@click.option("--project", is_flag=True,
              help="Write to this project's .visvoai/agents/ (shareable via the "
                   "repo; teammates approve it once) instead of ~/.visvoai/agents/.")
@click.option("--cwd", default=".", help="Project directory (with --project).")
def agents_create(name: str, project: bool, cwd: str) -> None:
    """Create an agent interactively (description → tools → model → prompt)."""
    from visvoai.cli.agents import BUILTIN_AGENTS, write_agent_file

    if name in BUILTIN_AGENTS:
        raise click.UsageError(f"'{name}' is a built-in agent — pick another name.")
    path = _agents_dir(project, cwd) / f"{name}.md"
    if path.exists() and not click.confirm(f"{path} exists — overwrite?"):
        return

    description = click.prompt("Description (one line — the main agent reads this "
                               "to decide when to delegate)")
    tier = click.prompt("Tools", type=click.Choice(["read-only", "full", "custom"]),
                        default="read-only")
    if tier == "custom":
        tier = click.prompt("Tool names (comma-separated: read_file, run_shell, "
                            "edit_file, write_file, list_files, list_tree, "
                            "web_search, web_fetch)")
    model = click.prompt("Model deployment id (empty = the session's model)",
                         default="", show_default=False).strip() or None
    click.echo("System prompt (what this agent IS and how it should work; "
               "end with an empty line):")
    lines: list[str] = []
    while True:
        line = input()
        if not line and lines:
            break
        lines.append(line)
    try:
        out = write_agent_file(_agents_dir(project, cwd), name,
                               description=description, tools=tier, model=model,
                               prompt="\n".join(lines).strip())
    except ValueError as e:
        raise click.UsageError(str(e))
    click.echo(f"\nCreated agent '{name}' → {out}")
    click.echo("Edit that file to refine the prompt — changes apply on the next turn.")
    if project:
        click.echo("Project-defined agent: the TUI asks for one-time approval (/agents).")


@agents_group.command("remove")
@click.argument("name")
@click.option("--cwd", default=".", help="Project directory to resolve agents for.")
def agents_remove(name: str, cwd: str) -> None:
    """Remove an agent definition file (built-ins can't be removed)."""
    from visvoai.cli.agents import BUILTIN_AGENTS

    if name in BUILTIN_AGENTS:
        click.echo(f"'{name}' is a built-in agent — it can't be removed.", err=True)
        sys.exit(1)
    removed = []
    for project in (False, True):
        path = _agents_dir(project, cwd) / f"{name}.md"
        if path.exists():
            path.unlink()
            removed.append(str(path))
    if removed:
        for p in removed:
            click.echo(f"Removed {p}")
    else:
        click.echo(f"No agent named '{name}' found.", err=True)
        sys.exit(1)


# ── `visvoai skills …` — manage skills ───────────────────────────────────────

def _skills_dir(project: bool, cwd: str):
    from visvoai.cli.skills import _skills_dir_global, _skills_dir_project
    return _skills_dir_project(os.path.abspath(cwd)) if project else _skills_dir_global()


@cli.group("skills")
def skills_group() -> None:
    """Manage skills (reusable workflow instructions the AI loads on demand).

    \b
    visvoai skills list                  merged roster (global + project)
    visvoai skills create release-notes  interactive: description, args, steps
    visvoai skills show release-notes    print a definition
    visvoai skills remove release-notes

    A skill is a directory: ~/.visvoai/skills/<name>/SKILL.md (global) or
    .visvoai/skills/<name>/SKILL.md (project, shareable via the repo;
    teammates approve it once in /skills). Supporting reference files live
    next to SKILL.md and are loaded only when the instructions call for them.
    """


@skills_group.command("list")
@click.option("--cwd", default=".", help="Project directory to resolve skills for.")
def skills_list(cwd: str) -> None:
    """List the merged skill roster."""
    from visvoai.cli.skills import is_trusted, load_skill_specs

    abs_cwd = os.path.abspath(cwd)
    specs = load_skill_specs(abs_cwd)
    if not specs:
        click.echo("No skills defined.\n"
                   "Create one:  visvoai skills create <name>   |   "
                   "write ~/.visvoai/skills/<name>/SKILL.md")
        return
    for s in specs.values():
        flags = []
        if s.source == "project" and not is_trusted(abs_cwd, s):
            flags.append("awaiting approval (/skills in the TUI)")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        args = (" (args: " + ", ".join(f"${a}" for a in s.args) + ")") if s.args else ""
        click.echo(f"{s.name:<20} {s.source:<8} {s.description}{args}{suffix}")


@skills_group.command("show")
@click.argument("name")
@click.option("--cwd", default=".", help="Project directory to resolve skills for.")
def skills_show(name: str, cwd: str) -> None:
    """Print a skill's full definition (instructions included)."""
    from visvoai.cli.skills import load_skill_specs

    spec = load_skill_specs(os.path.abspath(cwd)).get(name)
    if spec is None:
        click.echo(f"No skill named '{name}'.", err=True)
        sys.exit(1)
    click.echo(f"name:        {spec.name}")
    click.echo(f"source:      {spec.source}" + (f"  ({spec.path})" if spec.path else ""))
    click.echo(f"description: {spec.description}")
    if spec.args:
        click.echo("args:        " + ", ".join(f"${k} ({v})" for k, v in spec.args.items()))
    res = spec.resource_names()
    if res:
        click.echo("resources:   " + ", ".join(res))
    click.echo("\n--- instructions ---")
    click.echo(spec.body)


@skills_group.command("create")
@click.argument("name")
@click.option("--project", is_flag=True,
              help="Write to this project's .visvoai/skills/ (shareable via the "
                   "repo; teammates approve it once) instead of ~/.visvoai/skills/.")
@click.option("--cwd", default=".", help="Project directory (with --project).")
def skills_create(name: str, project: bool, cwd: str) -> None:
    """Create a skill interactively (description → args → instructions)."""
    from visvoai.cli.skills import write_skill_file

    path = _skills_dir(project, cwd) / name / "SKILL.md"
    if path.exists() and not click.confirm(f"{path} exists — overwrite?"):
        return
    description = click.prompt("Description (one line — the AI reads this to "
                               "decide when to load the skill)")
    args: dict = {}
    while True:
        arg = click.prompt("Add an arg? name (empty = done)", default="",
                           show_default=False).strip()
        if not arg:
            break
        args[arg] = click.prompt(f"  ${arg} description")
    click.echo("Instructions (the steps to follow; use $arg placeholders; "
               "end with an empty line):")
    lines: list[str] = []
    while True:
        line = input()
        if not line and lines:
            break
        lines.append(line)
    try:
        out = write_skill_file(_skills_dir(project, cwd), name,
                               description=description, args=args,
                               body="\n".join(lines).strip())
    except ValueError as e:
        raise click.UsageError(str(e))
    click.echo(f"\nCreated skill '{name}' → {out}")
    click.echo("Add supporting reference files next to SKILL.md; edit the file "
               "to refine — changes apply on the next turn.")
    if project:
        click.echo("Project-defined skill: the TUI asks for one-time approval (/skills).")


@skills_group.command("remove")
@click.argument("name")
@click.option("--cwd", default=".", help="Project directory to resolve skills for.")
def skills_remove(name: str, cwd: str) -> None:
    """Remove a skill definition (directory or flat file)."""
    import shutil

    removed = []
    for project in (False, True):
        root = _skills_dir(project, cwd)
        d = root / name
        f = root / f"{name}.md"
        if d.is_dir():
            shutil.rmtree(d)
            removed.append(str(d))
        elif f.exists():
            f.unlink()
            removed.append(str(f))
    if removed:
        for p in removed:
            click.echo(f"Removed {p}")
    else:
        click.echo(f"No skill named '{name}' found.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
