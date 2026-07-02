# widgets

Reusable Textual widgets in the "Style-B wired-schematic" identity. Each owns its
styling via `DEFAULT_CSS` and pulls colours only from `theme.py`, so it renders
consistently wherever mounted. `__init__.py` is the re-export surface.

# Key Files
- `conversation.py` → conversation-stream widgets: `UserMsg` (turn anchor), `Assistant` (streaming markdown, keeps `_raw` for mermaid split), `Thinking` (collapsible, hover-brighten), `TurnFooter`, `WorkingIndicator`.
- `welcome.py` → launch chrome: `Welcome`, `WelcomeBanner` (factory-driven so they re-theme).
- `tool_row.py` → Style-B tool wire: `ToolRow` / `ToolGroup` / `ToolNode` (auto-clustering, hover-brighten) + `ToolErrorBody`; `VERB_MAP`/`TOOL_DISPLAY` maps.
- `diff.py` → `CleanDiff` (pygments-highlighted side-by-side / unified diff).
- `output.py` → `ToolOutput` / `ShowMore`; `output_toolbar.py` → `OutputToolbar` / `SearchInput` / `SearchRow` (in-output search); `streaming_output.py`, `severity_output.py`, `read_chain.py`.
- `selection.py` / `form.py` / `free_text.py` → inline HITL widgets.
- `plan.py`, `system_note.py`, `error.py`, `reconciliation.py`, `citation.py`, `structure_tree.py`, `file_creation.py` → notices / structured blocks.
- `status.py` → `StatusBar` (model line + cumulative cost + context gauge with token label); `slash.py` → `SlashMenu`; `prompt.py` → `PromptArea` (paste-pill + slash/@ keys); `file_menu.py` → `FileMenu` (@-mention picker).
- `mermaid_card.py` → `MermaidCard` — the clickable inline diagram card.

# Conventions
- **The 9-class system**: every stream block belongs to one class with one identity rule — 1 user input (accent wash + ❯), 2 agent prose (plain foreground), 3 reasoning (dim/collapsible), 4 tool activity (wire + semantic verb accent), 5 tool results (panel bg, capped), 6 HITL asks (warning rail — the only blocking class), 7 errors (error accent + kind icon, never dim), 8 system notices (muted one-liners; kinds/icons from `iconography.NOTE_KINDS`), 9 milestones (◈ + rules/hairlines). New widgets must pick a class and inherit its rule.
- Glyphs come from `iconography.py` (NOTE_KINDS, STATE_STYLE, MILESTONE ◈ …) — never defined locally. ⎇ means git ONLY; conversation branches/checkpoints use ◈.
- Colours only from `theme.palette(self)`; never hardcode hex. Indentation numbers live only in `grid.py`.
- Inline Rich styles override CSS `color`, so hover/state effects re-render via a tracked flag (see `Thinking`/`ToolRow`).

# Gotchas
- `Assistant` subclasses Textual `Markdown` and keeps a `_raw` buffer (Markdown.append discards source) — the mermaid reflow needs it.
- Widgets with timers (spinners) must stop them in `on_unmount` to avoid post-teardown warnings.
