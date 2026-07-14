# Examples

Small, runnable, honest — each file teaches one thing and states exactly what
it needs (several run with **no API key**).

## The runtime (`visvoai-ai` + `visvoai-core`)

| File | Teaches | Needs a key? |
|---|---|---|
| [`01_hello_model.py`](./01_hello_model.py) | one line to any provider's streaming model | yes |
| [`02_choose_and_meter.py`](./02_choose_and_meter.py) | the registry: pick models by facts (price, context, thinking), meter cost per call | listing: **no** · metering: yes |
| [`03_minimal_agent.py`](./03_minimal_agent.py) | a working agent in ~20 lines — plain `@tool` functions + the core loop | yes |
| [`04_streaming_events.py`](./04_streaming_events.py) | live streaming UI pattern — the same event loop the visvoai-cli TUI is built on | yes |
| [`05_extend_the_runtime.py`](./05_extend_the_runtime.py) | the three extension seams: tool lifecycle, injected persistence, runtime hooks | **no** |
| [`06_tool_retrieval.py`](./06_tool_retrieval.py) | **the 300-tools problem**: index a tool fleet, bind only the relevant slice per request | **no** |
| [`07_sqlite_audit_trail.py`](./07_sqlite_audit_trail.py) | a real `ToolPersistence`: every tool call (incl. failures) audited into SQLite in ~30 lines | **no** |

```bash
pip install visvoai-core "visvoai-ai[gemini]"
export GEMINI_API_KEY=...
python examples/03_minimal_agent.py
```

## The CLI (`visvoai-cli`) — copy-paste configuration

| File | What it is | Where it goes |
|---|---|---|
| [`cli/agents/reviewer.md`](./cli/agents/reviewer.md) | a read-only reviewer subagent | `.visvoai/agents/reviewer.md` (project) or `~/.visvoai/agents/` (yours) |
| [`cli/release-notes/`](./cli/release-notes/) | a simple skill: one arg + a lazily-loaded reference file | `~/.visvoai/skills/release-notes/` |
| [`cli/pr-review/`](./cli/pr-review/) | a **complex** skill: classify first, then load only the branch's checklist (progressive disclosure across 3 reference files) | `~/.visvoai/skills/pr-review/` |
| [`cli/mytools.py`](./cli/mytools.py) | plugin tools in all three shapes: ungated read · approve-gated action · async | `~/.visvoai/tools/mytools.py` |
| [`cli/config.toml`](./cli/config.toml) | MCP servers + external skill libraries | `~/.visvoai/config.toml` |

### MCP in two commands

```bash
visvoai mcp add chrome -- npx -y chrome-devtools-mcp@latest
visvoai            # then: "open localhost:3000 and run a lighthouse audit"
```

Sessions are persistent (the browser keeps its pages between calls);
project-defined servers ask for your one-time approval in `/mcp`. Pair this
with `06_tool_retrieval.py` to see how a runtime consumer keeps big MCP
fleets bindable.

Then just talk to it: *"have the reviewer agent look at my diff"*, *"draft
release notes since v1.2"* — the CLI surfaces anything that needs your
one-time approval.
