# packages

Public open-core Python packages published under the `visvoai` namespace.

These are extracted from `backend/` during the decomposition on `visvoai/decompose`.
All code currently lives in `backend/`; the packages here are stubs that will be
populated as migration progresses.

# Key Directories
- `visvoai-ai/` → Unified multi-provider LLM access (Gemini, Anthropic, OpenAI, Together)
- `visvoai-core/` → Extensible agent runtime (AgentRuntime, BaseAgentTool, ToolRegistry, RuntimeContext, ToolPersistence)
- `visvoai-cli/` → Developer tool CLI (file/shell tools, CLIContext, stdout streaming, REPL)

# Conventions
- Namespace package: `visvoai.*` — no `__init__.py` at the `visvoai/` level (PEP 420)
- src layout: all package code lives under `src/visvoai/<subpackage>/`
- Dependency order: visvoai-cli → visvoai-core → visvoai-ai
- visvoai-ai has no internal cross-dependencies (pure LLM provider abstraction)

# Gotchas
- The `visvoai` namespace is shared across all three packages — installing two of them side-by-side requires namespace packages (no `__init__.py` at the namespace level)
- visvoai-core depends on langgraph; keep that dependency honest — CLI tools don't need the full graph machinery
