"""
visvoai.cli.main — CLI entry point.

Usage:
  visvoai "your prompt here"
  visvoai --cwd /path/to/project "refactor the auth module"
  visvoai --model gemini-2.5-pro "write tests for the new feature"

Runs an agent loop that can read/edit files, run shell commands, and stream
its thinking to the terminal.
"""
import asyncio
import os
import sys

import click
from langchain_core.messages import HumanMessage

_SYSTEM_PROMPT = """\
You are a developer tool. You have access to the local filesystem and a shell.

Your job: help the developer with coding tasks — reading files, editing code,
running tests, refactoring, debugging, and explaining what you find.

Rules:
- Be precise and minimal. Only change what the task requires.
- Before editing, always read the file first.
- Prefer edit_file over write_file for existing files — edit is safer.
- When running shell commands, prefer read-only commands unless a change is requested.
- After making changes, verify by reading the file back or running relevant tests.
"""


@click.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option(
    "--model",
    default="gemini-2.5-flash",
    show_default=True,
    help="Model API ID to use.",
)
@click.option(
    "--cwd",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    show_default=True,
    help="Working directory for file operations.",
)
@click.option("--verbose", is_flag=True, help="Show tool inputs and outputs.")
def cli(prompt: tuple, model: str, cwd: str, verbose: bool) -> None:
    """VisvoAI — AI developer tool. Edits files and runs commands in your codebase."""
    full_prompt = " ".join(prompt)
    asyncio.run(_run(full_prompt, model, os.path.abspath(cwd), verbose))


async def _run(prompt: str, model_id: str, cwd: str, verbose: bool) -> None:
    # Set cwd for subprocess calls (run_shell tool inherits this)
    os.chdir(cwd)

    # Model — resolve the provider from the registry so --model works across
    # families (Gemini, Anthropic, OpenAI-compatible). The provider reads its own
    # API key from the matching env var; build_chat_model lazily imports the
    # LangChain integration for that family.
    from visvoai.ai import get_model, get_provider

    md = get_model(model_id)
    provider_name = md.provider if md else "gemini"
    try:
        model = get_provider(provider_name).build_chat_model(model_id=model_id)
    except ImportError as e:
        click.echo(
            f"ERROR: the LangChain integration for provider '{provider_name}' is not "
            f"installed ({e}). Install the matching extra, e.g. "
            f"pip install 'visvoai-ai[{provider_name}]'.",
            err=True,
        )
        sys.exit(1)
    except KeyError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    # Tools
    from visvoai.cli.tools import build_cli_tools
    tools = build_cli_tools(cwd=cwd)
    tools_map = {t.name: t for t in tools}

    # Runtime + graph
    from visvoai.cli.runtime import CLIRuntime
    runtime = CLIRuntime()
    graph = runtime.build_graph(
        model=model,
        core_tools=tools,
        all_tools_map=tools_map,
        system_prompt=_SYSTEM_PROMPT,
    )

    # Stream the agent loop to stdout
    state = {"messages": [HumanMessage(content=prompt)]}

    try:
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    click.echo(chunk.content, nl=False)

            elif kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                if verbose:
                    inputs = event["data"].get("input", {})
                    click.echo(f"\n\n[tool: {tool_name}] {inputs}", err=True)
                else:
                    click.echo(f"\n[{tool_name}]", err=True)

            elif kind == "on_tool_end" and verbose:
                output = event["data"].get("output", "")
                preview = str(output)[:200] + ("…" if len(str(output)) > 200 else "")
                click.echo(f"  → {preview}", err=True)

    except KeyboardInterrupt:
        click.echo("\n[interrupted]", err=True)

    click.echo()  # trailing newline after streamed response


if __name__ == "__main__":
    cli()
