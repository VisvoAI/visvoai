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


@click.command()
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
@click.option(
    "--set-key",
    "set_key_provider",
    default=None,
    metavar="PROVIDER",
    help="Store an API key for a provider (e.g. gemini), then exit. Prompts for the "
         "key (hidden) and where to save it (global or this project).",
)
def cli(prompt: tuple, model: str, cwd: str, resume: str, verbose: bool,
        set_key_provider: str) -> None:
    """VisvoAI — terminal coding agent. Run with no prompt for the interactive TUI,
    or pass a prompt for a single-shot stream."""
    abs_cwd = os.path.abspath(cwd)
    if set_key_provider:
        _set_key_flow(set_key_provider, abs_cwd)
        return
    text = " ".join(prompt).strip()
    if text:
        asyncio.run(_run_single_shot(text, model, abs_cwd, verbose))
    else:
        _launch_tui(model, resume, abs_cwd)


def _bootstrap_env(cwd: str) -> None:
    """Make provider keys available before any model is built — for BOTH surfaces.
    Loads the nearest .env, then fills os.environ from the stored key layers
    (project secrets → global config) for anything not already set."""
    from dotenv import load_dotenv
    from visvoai.cli.keys import load_keys_into_env

    load_dotenv()                  # .env → os.environ (counts as the env layer)
    load_keys_into_env(cwd)        # project/global stored keys fill the rest


def _set_key_flow(provider: str, cwd: str) -> None:
    """Headless `--set-key`: prompt (hidden) for the key + scope, store it."""
    from visvoai.cli import keys

    key = click.prompt(f"{keys.env_var_for(provider)}", hide_input=True).strip()
    if not key:
        click.echo("No key entered — nothing saved.", err=True)
        return
    scope = click.prompt(
        "Save where? [g]lobal (~/.visvoai) or [p]roject (.visvoai, gitignored)",
        type=click.Choice(["g", "p"]), default="g", show_choices=False,
    )
    path = keys.set_key(provider, key, "global" if scope == "g" else "project", cwd)
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


async def _run_single_shot(prompt: str, model: str | None, cwd: str, verbose: bool) -> None:
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

    from visvoai.cli.runtime import CLIRuntime
    from visvoai.cli.tools import build_cli_tools

    tools = build_cli_tools(cwd=cwd)
    graph = CLIRuntime().build_graph(
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

    click.echo()  # trailing newline after the streamed response


if __name__ == "__main__":
    cli()
