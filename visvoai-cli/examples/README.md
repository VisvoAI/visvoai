# visvoai-cli examples — copy-paste configuration

Everything the CLI can be taught lives in files. Copy these to the listed
destination; the CLI picks them up next session and surfaces anything that
needs your one-time approval.

| Example | What it is | Copy to |
|---|---|---|
| [`agents/reviewer.md`](./agents/reviewer.md) | a read-only reviewer subagent | `.visvoai/agents/` (project) or `~/.visvoai/agents/` (yours) |
| [`skills/release-notes/`](./skills/release-notes/) | a simple skill: one arg + a lazily-loaded reference file | `~/.visvoai/skills/release-notes/` |
| [`skills/pr-review/`](./skills/pr-review/) | a **complex** skill: classify first, then load only that branch's checklist (progressive disclosure, 3 reference files) | `~/.visvoai/skills/pr-review/` |
| [`tools/mytools.py`](./tools/mytools.py) | plugin tools in all three shapes: ungated read · approve-gated action · async | `~/.visvoai/tools/` |
| [`config.toml`](./config.toml) | MCP servers + external skill libraries (`~/.claude/skills`) | `~/.visvoai/config.toml` |

### MCP in two commands

```bash
visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest
visvoai        # then: "open localhost:3000 and run a lighthouse audit"
```

Sessions are persistent (a browser keeps its pages between calls);
project-defined servers ask for one-time approval in `/mcp`.

Then just talk to it: *"have the reviewer agent look at my diff"*, *"use the
pr-review skill on my working tree"*, *"draft release notes since v1.2"*.
