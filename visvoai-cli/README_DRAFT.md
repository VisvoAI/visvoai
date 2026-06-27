# visvoai-cli

A developer-tool CLI built on [`visvoai-core`](https://pypi.org/project/visvoai-core/).
The agent reads and edits local files, runs shell commands, and searches the
web — streaming its work to the terminal. It is also the reference example of
consuming `visvoai-core` to build a real surface.

## Install

```bash
pip install visvoai-cli
```

That's everything — `visvoai-core`, `visvoai-ai`, and **all** provider
integrations (Gemini, Anthropic, OpenAI + any OpenAI-compatible provider). The
model picker's full catalog works out of the box; you only supply an API key for
the provider you use. The base install bundles `visvoai-ai[all]` on purpose: the
picker exposes every model, so any provider must be runnable (a Gemini-only
install would crash on selecting a Claude model).

### From source (local checkout)

Install as an editable command on your PATH — code changes are picked up live:

```bash
uv tool install --editable path/to/visvoai-cli
# then, from any directory:
visvoai
```

## Usage

The `visvoai` command has two surfaces: a single-shot stdout stream when you
pass a prompt, or an interactive Textual TUI when you don't.

```bash
export GEMINI_API_KEY=...
visvoai "list the Python files in the current directory"   # single-shot
visvoai                                                    # interactive TUI

visvoai --cwd ./myproject "add type hints to utils.py"     # run against another dir
visvoai --model gemini:gemini-3-flash-preview "..."        # pick a deployment
visvoai --yes "refactor the auth module"                   # auto-approve mutations
visvoai --resume                                            # resume the last TUI conversation
```

Provider keys resolve from environment variables (`GEMINI_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …) or the nearest `.env`. They can also
be stored (project or global) without polluting the shell:

```bash
visvoai --set-key gemini    # prompt for the key, then exit
```

Run `visvoai --help` for the full option list.

### The built-in tools

| Tool        | What it does                                    |
|-------------|-------------------------------------------------|
| `read_file` | Read a file (paginated, long lines clipped)     |
| `write_file`| Write a file (confined to `--cwd`)              |
| `edit_file` | Replace the first occurrence of a string        |
| `list_files`| List a directory                                |
| `list_tree` | Show a directory tree (bounded depth/width)     |
| `run_shell` | Run a shell command (30s timeout, output capped)|
| `web_search`| Grounded web search (provider-grounded answer)  |
| `web_fetch` | Fetch one URL → clean markdown                   |

Write/edit/shell are **path-confined** to `--cwd` (+ any configured extra
roots). In single-shot (headless) mode, mutating tools are **denied** unless
you pass `--yes` (auto-approve) or pre-authorize them in
`.visvoai/config.toml`. Path confinement applies either way.

## How it consumes visvoai-core

`CLIRuntime` subclasses `AgentRuntime` and injects a checkpointer and a
Textual-aware tools node through the core hook methods. The single-shot path
uses the same runtime:

```python
from visvoai.ai import build_chat_model, default_deployment
from visvoai.cli.runtime import CLIRuntime
from visvoai.cli.tools import build_cli_tools

model = build_chat_model("gemini:gemini-3-flash-preview")
tools = build_cli_tools(cwd="/path/to/project")
graph = CLIRuntime().build_graph(
    model=model,
    core_tools=tools,
    all_tools_map={t.name: t for t in tools},
    system_prompt="...",
)
```

## License

MIT
