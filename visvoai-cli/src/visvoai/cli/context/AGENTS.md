# context

Configurable per-turn system-prompt assembly for the CLI. Replaces the single
static prompt with an ordered set of budgeted providers, composed every turn and
driven by a layered `.visvoai/context.toml`. Slots into `CLIRuntime._build_agent_node`.

# Key Files
- `protocol.py` → `ContextProvider` base (name/cadence/order/budget + `render`), `ContextSection` dataclass.
- `assembler.py` → `ContextAssembler` (static cache + per-turn render + budgeting), `clip_to_tokens`, `estimate_tokens`, `rounds_this_turn`.
- `providers.py` → the 5 v1 providers (base_prompt, project_instructions, environment, datetime, git_state).
- `config.py` → load + layer the `[context]` table (global → project), apply to providers, resolve global budget.
- `__init__.py` → `build_assembler(system_prompt, cwd)` — the single entry point.

# Key Classes / Functions
- `ContextAssembler.assemble(state, finalize=False)` → the full system prompt: `[static block]` ++ `[per_turn block]`, each section clipped to its own budget, the whole clamped to the global budget; `finalize=True` appends the forced-finalize instruction.
- `build_assembler(system_prompt, cwd)` → constructs the v1 providers, applies config, returns a ready assembler.
- `rounds_this_turn(messages)` → agent rounds since the last human message; drives the soft-step-cap finalize (local copy of the core helper).

# Conventions
- Two cadences: `static` (rendered once, cached for the session → the cacheable prefix) and `per_turn` (re-rendered each turn → the volatile suffix). Static ALWAYS precedes per_turn so the prefix stays byte-stable; `order` sorts only WITHIN each block.
- Over-budget = truncate per-section (no LLM calls, no dropped sections), matching `tools/_common.py`.
- `render()` must never raise — the assembler swallows provider errors and omits the section; config errors are swallowed too.
- cwd-dependent providers receive cwd at construction — `GraphBuildContext` carries no cwd.

# Gotchas
- Token counts are a chars/4 heuristic, not a real tokenizer — budgets are coarse guardrails.
- `datetime` is deliberately `per_turn` so the current time stays OUT of the cacheable prefix.
- `git_state` uses `gitio.status_summary` (diff-free) — never `working_tree_status`, which computes diffs and is too heavy per turn.
- The pipeline is only active when `CLIRuntime` is built WITH an assembler; `CLIRuntime()` alone falls back to the core static-prompt node.
