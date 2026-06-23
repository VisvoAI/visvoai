# packages

Public open-core Python packages published under the `visvoai` namespace. These
are real, working, independently-installable libraries — the public surface of
the project. (They are also consumed internally by the private platform, which
extends them via subclassing + DI; that consumer is not described here.)

# Key Directories
- `visvoai-ai/` → Unified multi-provider LLM access (Gemini, Anthropic, OpenAI + OpenAI-compatible). Per-provider extras pull only the LangChain integration you use.
- `visvoai-core/` → Extensible agent runtime (AgentRuntime, BaseAgentTool, tool_config, RuntimeContext, AgentState, ToolResult/ToolStatus, ToolPersistence, ToolCatalog).
- `visvoai-cli/` → Developer-tool CLI (file/shell tools, CLIContext, CLIRuntime, stdout streaming) — the reference consumer of `visvoai-core`.

# Conventions
- Namespace package: `visvoai.*` — no `__init__.py` at the `visvoai/` level (PEP 420)
- src layout: all package code lives under `src/visvoai/<subpackage>/`
- Dependency order points DOWN only: visvoai-cli → visvoai-core → visvoai-ai
- visvoai-ai has no internal cross-dependencies (pure LLM provider abstraction)
- **No private/platform references in shipped code or docstrings.** Public docstrings describe the generic extension seam ("a consumer subclasses this to add X"), never a specific private consumer by name. Keep it that way when editing.
- Each package ships a `README.md` (referenced by its `pyproject.toml`); `packages/README.md` is the public monorepo landing page.

# Gotchas
- The `visvoai` namespace is shared across all three packages — installing two side-by-side relies on PEP 420 namespace packages (no `__init__.py` at the namespace level).
- visvoai-core depends on langgraph; keep that dependency honest — the CLI's plain `@tool` functions don't need the full graph machinery.
- LLM integration packages (`langchain-google-genai` / `-anthropic` / `-openai`) are declared as **per-provider extras** on `visvoai-ai`, imported lazily — the base install stays light. A consumer must install the matching extra (e.g. `visvoai-ai[gemini]`) or the lazy import fails at call time.
- This tree (`packages/`) is what `git subtree split --prefix=packages` extracts to the public `visvoai` repo — its top level becomes the public repo root. Nothing outside `packages/` ships publicly.
