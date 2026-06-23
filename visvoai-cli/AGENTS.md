# visvoai-cli

> ⚠️ **PLACEHOLDER — not a working consumer.** This package is an early scaffold,
> NOT a reference implementation. Its tools are plain LangChain `@tool` functions,
> it does not exercise `BaseAgentTool`, and nothing here validates the core
> contract. Do not treat the CLI as a consumer when reasoning about the core/ai
> public API. The real CLI work begins only after `visvoai-core` and `visvoai-ai`
> are finalized — at which point this is rebuilt to genuinely dogfood the seams.

Developer tool CLI built on visvoai-core: an agent that edits the filesystem, runs
shell commands, and streams output to the terminal.

# Key Files (to be created in Step 6)
- `src/visvoai/cli/main.py` → Click CLI entry point, REPL loop
- `src/visvoai/cli/context.py` → CLIContext(RuntimeContext) — CLI-specific state
- `src/visvoai/cli/streaming.py` → stdout streaming adapter (ToolCallDTO → terminal)
- `src/visvoai/cli/tools/` → file_read, file_edit, file_write, shell, list_files

# Key Classes / Functions (planned)
- `CLIContext(RuntimeContext)` → adds cwd, terminal_width; no DB/auth fields
- `CLIRuntime(AgentRuntime)` → _extend_graph() adds no platform nodes (pure core loop)
- `cli` → Click group entry point (registered as `visvoai` console script)

# Conventions
- No langgraph interrupts — CLI is synchronous, no HITL (user is already in the loop)
- Tools write to stdout via Rich; no SSE, no WebSockets
- CLIContext must not import BackendContext or any platform modules

# Gotchas
- Step 6 is not yet implemented — this package is a stub as of the decompose branch
