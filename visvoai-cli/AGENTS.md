# visvoai-cli

A working developer-tool CLI built on `visvoai-core`: an agent that reads and
edits the filesystem, runs shell commands, and streams output to the terminal.
It is the reference example of consuming the runtime from a real surface.

It is intentionally minimal — plain LangChain `@tool` functions, a synchronous
loop, no checkpointer — to keep the consuming pattern easy to read. Expect it to
grow; keep new additions just as small and dependency-light.

# Key Files
- `src/visvoai/cli/main.py` → Click entry point; builds the model + graph, streams `astream_events` to stdout
- `src/visvoai/cli/context.py` → `CLIContext(RuntimeContext)` — CLI-specific state (cwd, terminal width)
- `src/visvoai/cli/runtime.py` → `CLIRuntime(AgentRuntime)` — adds no extra nodes (pure core loop)
- `src/visvoai/cli/tools/__init__.py` → file + shell tools as plain LangChain `@tool` functions

# Key Classes / Functions
- `CLIContext(RuntimeContext)` → adds cwd / terminal width; no auth or datastore fields
- `CLIRuntime(AgentRuntime)` → `_extend_graph()` adds nothing — the default agent→tools loop
- `cli` → Click entry point (registered as the `visvoai` console script)

# Conventions
- No graph interrupts — the CLI is synchronous (the user is already in the loop)
- Tools write to stdout via Rich; no SSE, no WebSockets
- Tools are plain `@tool` functions (not `BaseAgentTool`) — demonstrates that `visvoai-core` binds any LangChain `BaseTool`
- `CLIContext` must not import any private/consumer modules — only `visvoai-core`

# Gotchas
- The default model is Gemini, built directly in `main.py` via `langchain-google-genai` (declared as a dependency). Set `GEMINI_API_KEY` before running.
