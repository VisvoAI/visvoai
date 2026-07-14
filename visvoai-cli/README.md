# visvoai-cli

**A terminal coding agent that takes permissions seriously.**

A full-screen TUI agent (built on [Textual](https://textual.textualize.io/))
that reads, edits, and runs code in your repo — with a permission model
enforced by the OS, not by politeness; delegatable subagents with live logs;
teachable skills; MCP; and per-turn time-travel across both your files and the
conversation.

```bash
pip install visvoai-cli
export GEMINI_API_KEY=...     # or ANTHROPIC_API_KEY / OPENAI_API_KEY / any compatible
visvoai
```

All provider integrations ship in the box — the model picker exposes a live
catalog (Gemini, Claude, GPT, Together, Groq, OpenRouter, …); you only supply
a key for the provider you use. `visvoai "fix the failing test"` runs a
single-shot turn without the TUI.

---

## Why this one

**The shell is gated by the kernel, not the prompt.** Every shell command is
classified read vs write. Reads (`ls`, `rg`, `git log`, …) run instantly —
inside an OS no-write sandbox (macOS `sandbox-exec`, Linux `bwrap`), so a
write disguised as a read fails with a kernel error instead of mutating your
disk. Writes ask you first. The classifier only decides *prompting*; the
sandbox is the boundary, so a misclassification is an inconvenience, never an
incident.

**Everything repo-defined needs your one-time approval.** Project agents,
skills, and MCP servers are files a repo controls — each is hashed and
requires explicit trust before the model can use it; any edit re-prompts.
What *you* define globally is implicitly yours. Cloning a repo can never
silently arm anything.

**Time-travel that includes your files.** Every turn checkpoints the working
tree in a shadow git repo. `/rewind` restores files + conversation together;
timelines branch; `/fork` opens a checkpoint in a fresh directory to explore
in parallel.

## Agents & subagents

Delegate self-contained work; run dispatches in parallel; watch them live.

```markdown
<!-- .visvoai/agents/reviewer.md -->
---
description: Reviews a diff for bugs and risky changes
tools: read-only
---
You are a meticulous code reviewer. Examine the diff, read surrounding
context, and report concrete findings with file:line references.
```

- Built-ins ship ready: `explore` (read-only, parallel-friendly recon) and
  `general` (full toolset — its mutations still ask *you*).
- Each dispatch is an isolated conversation: own prompt, own tools, fresh
  history; only its final answer returns to the caller.
- **Live everywhere**: a side panel shows running agents' tool steps as they
  execute; `/runs` gives full logs with per-run stop; every dispatch persists
  a JSONL trace with tokens · cost · duration.
- Tool tiers are fixed at build time — an agent can't talk itself into more
  capability, and a read-only agent needs zero approval prompts to work.

## Skills

Teach a workflow once; the agent loads it when a request matches — index
first, full instructions on demand, referenced files only when the steps call
for them (progressive disclosure).

```markdown
<!-- ~/.visvoai/skills/release-notes/SKILL.md -->
---
description: Draft release notes from the git log
args:
  version: The version being released
---
1. Run `git log $version..HEAD --oneline`.
2. Group changes by type; see checklist.md for the house format.
```

Already have skill libraries? Point at them:

```toml
# ~/.visvoai/config.toml
[skills]
extra_dirs = ["~/.claude/skills", "~/dotfiles/skills"]
```

A skill grants knowledge, never capability — the agent follows the steps with
its own gated tools.

## MCP

```bash
visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest
visvoai mcp add linear --url https://mcp.linear.app/mcp \
    --header 'Authorization=Bearer ${LINEAR_API_KEY}'
```

Sessions are persistent, so stateful servers (a browser, a DB connection)
keep their state across calls. Secrets stay `${VAR}` references — never in
config files.

## Plugin tools

```python
# ~/.visvoai/tools/mytools.py
from visvoai.cli.toolkit import make_cli_tool

def jira_search(query: str, limit: int = 10) -> str:
    """Search our Jira and return matching issue keys."""
    ...

TOOLS = [make_cli_tool(jira_search, gate="approve")]
```

Schema from your type hints, description from the docstring, output capped,
exceptions returned as data, approval-gated by declaration. Global-only by
design — a repo can never inject Python into your session.

## Living in it

| | |
|---|---|
| `/model` | live model catalog — pricing, thinking levels, per-conversation |
| `/agents` `/skills` `/mcp` | rosters + one-time trust approval |
| `/runs` | live subagent logs; stop one without killing the turn |
| `/rewind` `/branch` `/fork` | time-travel: files + conversation together |
| `/ps` | background processes the agent started (and the kill switch) |
| `/compact` | summarize older turns to reclaim context |
| `Shift+Tab` | approval mode: normal · auto-edit · accept-all |
| `@file` | attach a file; `Esc` stops the turn; full mouse support |

Costs and context are always visible: per-turn tokens/cost in the footer, a
context gauge that warns before you hit the wall.

## From source

```bash
uv tool install --editable path/to/visvoai-cli
```

## Examples

Copy-paste configuration in [`examples/`](./examples/) — a reviewer agent, a
simple and a complex skill, plugin tools in all three shapes, and a
config.toml with MCP + external skill libraries.

## License

MIT
