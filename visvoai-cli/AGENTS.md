# visvoai-cli

Developer tool CLI built on visvoai-core. Reference implementation of what a
visvoai-core extension looks like: an agent that edits the filesystem, runs shell
commands, and streams output to the terminal.

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
