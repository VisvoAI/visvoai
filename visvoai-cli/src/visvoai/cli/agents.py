"""
Agents (subagents) for the CLI.

An agent is a named worker the main agent can delegate a task to via the
`run_agent` tool. Each dispatch builds a FRESH graph (own system prompt, own
tool set, empty history) — full isolation: the subagent sees only the task
text, and only its final answer returns to the caller. Multiple `run_agent`
calls in one turn run concurrently (LangGraph's ToolNode executes tool calls
in parallel), so fan-out search is natural.

Roster — three layers merged, later wins on name:

  built-ins (this file)               explore · general — always available
  ~/.visvoai/agents/<name>.md         global: personal agents, everywhere
  <project>/.visvoai/agents/<name>.md project: shareable, may be checked in

Definition file — markdown with frontmatter; the body is the system prompt:

  ---
  description: Reviews a diff for bugs and style issues
  tools: read-only            # read-only | full | comma-separated tool names
  model: gemini:gemini-3.1-flash   # optional — omit to use the session model
  ---
  You are a meticulous code reviewer. ...

Tool tiers (capability is fixed at graph build, never model-selectable):
  read-only → read/list/tree/web + a shell that REFUSES write-classified
              commands and runs reads inside the OS no-write sandbox. No
              approval prompts — nothing it can do mutates.
  full      → the standard tool set; mutating tools go through the SAME
              approve() gate as the top level (the user still sees prompts).
  Neither tier includes run_agent itself — depth is capped at 1.

Trust — a project agent's prompt drives tool use inside the repo owner's
machine, same threat model as a project MCP server: one-time approval recorded
outside the repo (`~/.visvoai/projects/<pid>/agent_trust.toml`) as a hash of
the definition; any change re-prompts. Global agents are implicitly trusted.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from langchain_core.tools import InjectedToolCallId

logger = logging.getLogger(__name__)

AGENT_RESULT_LINE_CAP = 400   # max lines of a subagent's final answer
MAX_TASK_CHARS = 20_000

# Tag on every run inside a subagent's graph (config tags propagate to child
# runs). astream_events BUBBLES nested-graph events into the main turn stream —
# without this tag the turn worker renders and PERSISTS the subagent's private
# messages as main-conversation history (live incident: 40 leaked messages and
# a dangling run_agent call). Full form `visvoai_subagent:<name>:<dispatch_id>`:
# the worker filters on the prefix; the name feeds the status pulse; the
# dispatch id (the run_agent tool_call_id) attributes events to ONE dispatch —
# parallel dispatches of the SAME agent are otherwise indistinguishable.
SUBAGENT_TAG_PREFIX = "visvoai_subagent:"


def subagent_key_from_tags(tags) -> tuple[str, str] | None:
    """(agent_name, dispatch_id) if this event belongs to a subagent run."""
    for t in tags or ():
        if isinstance(t, str) and t.startswith(SUBAGENT_TAG_PREFIX):
            rest = t[len(SUBAGENT_TAG_PREFIX):]
            name, _, dispatch = rest.partition(":")
            return name, dispatch
    return None


def subagent_name_from_tags(tags) -> str | None:
    """The dispatched agent's name if this event belongs to a subagent run."""
    key = subagent_key_from_tags(tags)
    return key[0] if key else None

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

READ_ONLY_TOOL_NAMES = ("read_file", "list_files", "list_tree",
                        "web_search", "web_fetch", "run_shell")


# ── Specs ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentSpec:
    name: str
    source: str                  # "builtin" | "global" | "project"
    description: str
    prompt: str                  # the subagent's system prompt
    tools: str = "read-only"     # "read-only" | "full" | "a,b,c" explicit names
    model: str | None = None     # deployment id; None → session model
    path: Path | None = None     # definition file (None for built-ins)

    def spec_hash(self) -> str:
        """Stable hash of the full definition — trust records for project agents.
        Unlike MCP (where secrets are excluded), everything here IS the executable
        surface: the prompt steers the tools."""
        surface = {"description": self.description, "prompt": self.prompt,
                   "tools": self.tools, "model": self.model}
        return hashlib.sha256(json.dumps(surface, sort_keys=True).encode()).hexdigest()[:16]


BUILTIN_AGENTS: dict[str, AgentSpec] = {
    "explore": AgentSpec(
        name="explore", source="builtin",
        description=("Fast read-only codebase/docs reconnaissance. Finds files, "
                     "usages, and conventions; reports conclusions, not file dumps. "
                     "Dispatch SEVERAL in parallel to search different corners."),
        tools="read-only",
        prompt=(
            "You are a fast read-only exploration agent inside a developer CLI. "
            "You search code and docs to answer ONE focused question.\n"
            "Your tools cannot modify anything: your shell rejects write commands "
            "and file writes are blocked at the OS level — don't attempt them.\n"
            "Work breadth-first: locate candidates (list_tree, run_shell with "
            "grep/rg/find, list_files), then read only the parts that answer the "
            "question. Prefer excerpts over whole files.\n"
            "Your FINAL message is returned verbatim to the agent that dispatched "
            "you — make it a dense, self-contained answer: concrete paths, line "
            "numbers, names, and the conclusion. No preamble, no 'let me know'."),
    ),
    "general": AgentSpec(
        name="general", source="builtin",
        description=("Multi-step delegated task with the full tool set (edits and "
                     "shell included — mutations still ask the user). Use for a "
                     "self-contained subtask you want done end-to-end."),
        tools="full",
        prompt=(
            "You are a delegated worker agent inside a developer CLI. You are "
            "handed ONE self-contained task; complete it end-to-end.\n"
            "You have the full tool set. Read before editing; verify changes by "
            "reading back or running tests. Mutating actions may ask the user "
            "for approval — a denial is an instruction, adapt rather than retry.\n"
            "Your FINAL message is returned verbatim to the agent that dispatched "
            "you — state what you did, what you verified, and anything left open. "
            "Be dense and concrete; no preamble."),
    ),
}


# ── Definition files ──────────────────────────────────────────────────────────

def _parse_agent_file(path: Path, source: str) -> AgentSpec | None:
    """Parse one `<name>.md` definition. Frontmatter keys: description, tools,
    model, name (optional — filename stem wins conflicts). Returns None (logged)
    on a malformed file — one bad agent must not break the roster."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("agents: unreadable %s: %s", path, e)
        return None
    name = path.stem
    if not _NAME_RE.match(name):
        logger.warning("agents: invalid agent name '%s' (%s) — skipped", name, path)
        return None
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
    prompt = body.strip()
    if not prompt:
        logger.warning("agents: %s has an empty prompt body — skipped", path)
        return None
    tools = meta.get("tools", "read-only").strip() or "read-only"
    return AgentSpec(
        name=name, source=source,
        description=meta.get("description", "").strip() or f"custom agent '{name}'",
        prompt=prompt, tools=tools,
        model=meta.get("model") or None,
        path=path,
    )


def _agents_dir_global() -> Path:
    from visvoai.cli.store import visvoai_home
    return visvoai_home() / "agents"


def _agents_dir_project(cwd: str) -> Path:
    from visvoai.cli.store import project_root
    try:
        return project_root(cwd) / ".visvoai" / "agents"
    except Exception:
        return Path(cwd) / ".visvoai" / "agents"


def _load_dir(directory: Path, source: str) -> dict[str, AgentSpec]:
    if not directory.is_dir():
        return {}
    out: dict[str, AgentSpec] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix == ".md":
            spec = _parse_agent_file(path, source)
            if spec:
                out[spec.name] = spec
        elif path.is_file() and not path.name.startswith("."):
            # A definition in the wrong format (e.g. .toml) would otherwise
            # vanish silently — the #1 way an agent-created agent "doesn't show".
            logger.warning("agents: %s ignored — definitions must be .md files "
                           "(frontmatter + prompt body)", path)
    return out


def stray_definition_files(cwd: str) -> list[Path]:
    """Non-.md files sitting in an agents directory — almost always a definition
    written in the wrong format. Surfaced by /agents so 'my agent doesn't show'
    is self-diagnosing."""
    strays: list[Path] = []
    for directory in (_agents_dir_global(), _agents_dir_project(cwd)):
        if directory.is_dir():
            strays += [p for p in sorted(directory.iterdir())
                       if p.is_file() and p.suffix != ".md"
                       and not p.name.startswith(".")]
    return strays


def load_agent_specs(cwd: str) -> dict[str, AgentSpec]:
    """Merged roster: built-ins ∪ global ∪ project (later wins on name)."""
    merged = dict(BUILTIN_AGENTS)
    merged.update(_load_dir(_agents_dir_global(), "global"))
    merged.update(_load_dir(_agents_dir_project(cwd), "project"))
    return merged


# ── Trust (project agents only — same model as project MCP servers) ─────────

def _trust_path(cwd: str) -> Path:
    from visvoai.cli.store import resolve_project_id, visvoai_home
    return visvoai_home() / "projects" / resolve_project_id(cwd) / "agent_trust.toml"


def _read_trust(cwd: str) -> dict[str, str]:
    path = _trust_path(cwd)
    if not path.exists():
        return {}
    try:
        return {k: v for k, v in (tomllib.loads(path.read_text()).get("trusted") or {}).items()
                if isinstance(v, str)}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def is_trusted(cwd: str, spec: AgentSpec) -> bool:
    if spec.source != "project":
        return True
    return _read_trust(cwd).get(spec.name) == spec.spec_hash()


def trust_agent(cwd: str, spec: AgentSpec) -> None:
    trusted = _read_trust(cwd)
    trusted[spec.name] = spec.spec_hash()
    path = _trust_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[trusted]"] + [f'{name} = "{h}"' for name, h in sorted(trusted.items())]
    path.write_text("\n".join(lines) + "\n")


def untrusted_agents(cwd: str) -> list[AgentSpec]:
    return [s for s in load_agent_specs(cwd).values() if not is_trusted(cwd, s)]


# ── Definition writing (`visvoai agents create` + the /agents flow) ─────────

AGENT_TEMPLATE = """\
---
description: {description}
tools: {tools}
{model_line}---

{prompt}
"""


def write_agent_file(directory: Path, name: str, *, description: str,
                     tools: str, model: str | None, prompt: str) -> Path:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid agent name '{name}' (use letters/digits/-/_)")
    if name in BUILTIN_AGENTS:
        raise ValueError(f"'{name}' is a built-in agent — pick another name "
                         "(a file would silently shadow it)")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(AGENT_TEMPLATE.format(
        description=description, tools=tools,
        model_line=f"model: {model}\n" if model else "",
        prompt=prompt,
    ), encoding="utf-8")
    return path


# ── Subagent tool sets ────────────────────────────────────────────────────────

def _tools_for_spec(spec: AgentSpec, cwd: str, approve, extra_tools=None,
                    process_registry=None) -> list:
    """The tool set a subagent gets — decided HERE at graph build, never by the
    model. read-only ⇒ reads + the write-refusing sandboxed shell, ungated.
    full ⇒ the standard set behind the same approve() gate as the top level.
    Explicit names ⇒ that subset of the full set (unknown names ignored).

    extra_tools (session MCP tools) join the full tier and are selectable by
    name in explicit lists — gated like any external action. They are NEVER in
    read-only: an MCP call's side effects can't be classified, and the OS
    sandbox doesn't cover a remote server."""
    from visvoai.cli.gated_tools import build_gated_tools, build_readonly_shell, gate_tool
    from visvoai.cli.tools import build_cli_tools, list_files, list_tree, read_file, web_fetch, web_search

    tier = spec.tools.strip().lower()
    if tier == "read-only":
        return [read_file, list_files, list_tree, web_search, web_fetch,
                build_readonly_shell()]
    if approve is not None:
        full = build_gated_tools(cwd=cwd, approve=approve)
        full += [gate_tool(t, approve) for t in (extra_tools or [])]
    else:
        full = build_cli_tools(cwd=cwd) + list(extra_tools or [])
    if process_registry is not None:
        # Background tools (start/check/stop_process, self-gating) — without
        # them a subagent has NO way to run a dev server except blocking its
        # synchronous shell until timeout (live incident: a Lighthouse agent
        # hung on a foreground `yarn dev`). Registry is the APP's — processes
        # show in /ps and die on app exit like any other.
        from visvoai.cli.tools.background import build_background_tools
        full += build_background_tools(process_registry, cwd=cwd, approve=approve)
    if tier == "full":
        return full
    wanted = {n.strip() for n in spec.tools.split(",") if n.strip()}
    wanted.discard("run_agent")          # depth cap: subagents never dispatch
    chosen = [t for t in full if t.name in wanted]
    return chosen or full                # empty selection → full (never a tool-less agent)


# ── The run_agent tool ────────────────────────────────────────────────────────

def _roster_description(specs: dict[str, AgentSpec]) -> str:
    lines = [
        "Delegate ONE self-contained task to a specialist subagent and get its "
        "final answer back. The subagent sees NONE of this conversation — only "
        "your task text (plus the project environment), so include all needed "
        "paths, names, and constraints. It cannot ask follow-up questions.",
        "Dispatch several run_agent calls IN PARALLEL (one message, multiple "
        "calls) when tasks are independent — e.g. three 'explore' agents "
        "searching different corners of a codebase.",
        "",
        "Available agents:",
    ]
    for spec in specs.values():
        lines.append(f"- {spec.name}: {spec.description}")
    lines += [
        "",
        "To CREATE a new agent (when asked to): write a MARKDOWN file at "
        ".visvoai/agents/<name>.md (this project) or ~/.visvoai/agents/<name>.md "
        "(all projects). NOT toml/json/yaml — .md only; other files are ignored. "
        "Format: frontmatter between --- lines with `description:` (one line), "
        "`tools:` (see below), optional `model:` (deployment id); then the BODY "
        "is the agent's system prompt. It joins this roster next turn.",
        "Choose the SMALLEST tools tier that fits: `read-only` for analysis/"
        "search/review agents; an explicit comma-separated list (e.g. `tools: "
        "read_file, list_files, run_shell`) when it must run commands but never "
        "edit files; `full` ONLY when it must modify files. Connected MCP tools "
        "(named server__tool) are included in `full` and selectable by name in "
        "explicit lists — never available in `read-only`.",
        "In the prompt BODY, describe capabilities ('audit via Lighthouse'), "
        "don't hardcode tool names — a named tool (especially server__tool MCP "
        "names) may not be connected when the agent runs, and stale names cause "
        "failed calls.",
        "After creating one, tell the user in plain language: they approve it "
        "once in /agents (project agents only), then simply ASK for the task — "
        "run_agent is YOUR internal tool, never a command the user types.",
    ]
    return "\n".join(lines)


def _telemetry_trailer(spec: AgentSpec, dep_id: str, messages: list,
                       duration_s: float) -> str:
    """The compact telemetry trailer appended to the tool result:
    `[agent: X · N tool calls · Yk tokens · $C · Ds]`."""
    from visvoai.cli.agent import turn_cost, usage_of

    tin = tout = 0
    rounds = 0
    for m in messages:
        kind = m.__class__.__name__
        if kind == "AIMessage":
            u = usage_of(m)
            tin += u["input"]; tout += u["output"]
        elif kind == "ToolMessage":
            rounds += 1
    cost = turn_cost(dep_id, tin, tout)
    trailer_bits = [f"agent: {spec.name}",
                    f"{rounds} tool call{'s' if rounds != 1 else ''}",
                    f"{(tin + tout) / 1000:.1f}k tokens"]
    if cost:
        trailer_bits.append(f"${cost:.4f}")
    trailer_bits.append(f"{duration_s:.0f}s")
    return "[" + " · ".join(trailer_bits) + "]"


def _write_headless_trace(trace_path: Path, spec: AgentSpec, dispatch_id: str,
                          task: str, dep_id: str, messages: list,
                          summary: str) -> None:
    """One-shot trace for runs WITHOUT a registry (headless single-shot). The
    TUI path traces live via AgentRunRegistry instead. Never raises."""
    from visvoai.cli.agent import chunk_text

    try:
        lines = [json.dumps({"kind": "meta", "agent": spec.name,
                             "dispatch_id": dispatch_id, "model": dep_id,
                             "tools": spec.tools, "task": task[:2000]})]
        for m in messages:
            kind = m.__class__.__name__
            if kind == "AIMessage":
                rec = {"kind": "ai", "text": chunk_text(m)[:4000]}
                if getattr(m, "tool_calls", None):
                    rec["tool_calls"] = [{"name": t.get("name"),
                                          "args": {k: str(v)[:500] for k, v in
                                                   (t.get("args") or {}).items()}}
                                         for t in m.tool_calls]
                lines.append(json.dumps(rec, ensure_ascii=False))
            elif kind == "ToolMessage":
                lines.append(json.dumps({"kind": "tool",
                                         "name": getattr(m, "name", None),
                                         "output": chunk_text(m)[:4000]},
                                        ensure_ascii=False))
        lines.append(json.dumps({"kind": "summary", "summary": summary}))
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning("agents: trace write failed (ignored): %s", e)


def build_run_agent_tool(cwd: str, deployment_id: str, approve=None,
                         level: str | None = None, extra_tools=None,
                         trace_dir_fn=None, process_registry=None,
                         run_registry=None):
    """The `run_agent(agent, task)` tool bound to this session's roster.

    Rebuilt every turn (like the rest of the graph) so file edits to agent
    definitions are picked up live. Untrusted project agents are EXCLUDED from
    the roster here — trust approval happens in /agents, not mid-turn.

    extra_tools: the session's discovered MCP tools, passed through to full-tier
    and explicit-list subagents (see _tools_for_spec).

    trace_dir_fn: () -> Path|None, resolved AT DISPATCH TIME (the conversation
    id doesn't exist yet when the graph is built on a fresh conversation).

    run_registry: the app's AgentRunRegistry. The TOOL owns the run lifecycle —
    it registers the run (it alone knows the real dispatch id, the task, and
    holds the cancellable asyncio task) and finishes it; the turn worker only
    feeds live steps. A /runs stop cancels the task here; the caller gets a
    plain 'stopped by user' result and the main turn survives. None (headless/
    tests) → the run executes identically, just untracked live.
    """
    from langchain_core.tools import StructuredTool

    specs = {n: s for n, s in load_agent_specs(cwd).items() if is_trusted(cwd, s)}

    async def _run_agent(agent: str, task: str,
                         tool_call_id: Annotated[str, InjectedToolCallId] = "") -> str:
        spec = specs.get(agent)
        if spec is None:
            known = ", ".join(specs)
            return f"ERROR: unknown agent '{agent}'. Available: {known}"
        if not task.strip():
            return "ERROR: empty task — describe what the agent should do."
        # The dispatch id: the run_agent tool_call_id (injected by the tool
        # infra, never model-supplied), unique per call even for parallel
        # dispatches of the same agent. Fallback uuid covers direct invocation
        # outside a graph (tests, headless edge paths).
        dispatch_id = tool_call_id or __import__("uuid").uuid4().hex[:12]

        import time as _time

        from langchain_core.messages import HumanMessage
        from visvoai.ai import build_chat_model
        from visvoai.cli.runtime import CLIRuntime
        from visvoai.cli.tools import cap_lines
        started = _time.monotonic()

        dep_id = spec.model or deployment_id
        try:
            # A custom agent's model applies its own default thinking; the
            # session model reuses the session's chosen level.
            model = build_chat_model(dep_id, level=level if spec.model is None else None)
        except Exception as e:
            return f"ERROR: agent '{agent}' model '{dep_id}' unavailable: {e}"

        tools = _tools_for_spec(spec, cwd, approve, extra_tools, process_registry)
        # A definition's prompt may name tools that aren't connected THIS
        # session (live incident: a prompt hardcoding chrome__* MCP tools made
        # the subagent call names it didn't have — prompt-following beats
        # function-declaration awareness), so counter it in the prompt itself.
        prompt = spec.prompt + (
            "\n\nTool reality check: you have ONLY the tools declared in this "
            "session. If these instructions mention a tool that is not "
            "declared, use the closest available alternative (usually the "
            "shell) — never call an undeclared tool name.")
        # Same per-turn context the main agent gets (environment/cwd, project
        # instructions, git state) — without an assembler the subagent doesn't
        # even know its working directory.
        from visvoai.cli.context import build_assembler
        graph = CLIRuntime(assembler=build_assembler(prompt, cwd)).build_graph(
            model=model,
            core_tools=tools,
            all_tools_map={t.name: t for t in tools},
            system_prompt=prompt,
        )
        # The run is a first-class citizen: registered before the first model
        # call, cancellable individually (a /runs stop cancels ONLY this task),
        # trace appended live by the registry as steps complete.
        import asyncio

        trace_path = None
        try:
            trace_dir = trace_dir_fn() if trace_dir_fn else None
            if trace_dir is not None:
                trace_path = Path(trace_dir) / f"{spec.name}_{dispatch_id[:12]}.jsonl"
        except Exception:
            trace_path = None

        invoke_task = asyncio.ensure_future(graph.ainvoke(
            {"messages": [HumanMessage(content=task[:MAX_TASK_CHARS])]},
            config={"recursion_limit": 100,
                    "tags": [f"{SUBAGENT_TAG_PREFIX}{spec.name}:{dispatch_id}"]},
        ))
        run = None
        if run_registry is not None:
            run = run_registry.register(dispatch_id, spec.name, task,
                                        trace_path=trace_path,
                                        cancel=invoke_task.cancel)
        try:
            result = await invoke_task
        except asyncio.CancelledError:
            # Awaiting a SEPARATE task means our own cancellation (Esc on the
            # turn) does NOT cancel it — without this the subagent graph keeps
            # running orphaned in the background (spending tokens, mutating
            # files after the user stopped the turn).
            invoke_task.cancel()
            if run is not None and run.user_stopped:
                run_registry.finish(dispatch_id, ok=False, summary="stopped by user")
                return (f"Agent '{agent}' was STOPPED BY THE USER before "
                        "finishing. Treat this as an instruction: don't retry "
                        "the same dispatch — ask what to do instead.")
            if run_registry is not None:
                run_registry.finish(dispatch_id, ok=False,
                                    summary="turn stopped (esc)")
            raise   # whole-turn cancellation — propagate
        except Exception as e:
            if run_registry is not None:
                run_registry.finish(dispatch_id, ok=False, summary=str(e)[:200])
            return f"ERROR: agent '{agent}' failed: {e}"

        messages = result.get("messages", [])
        final = ""
        for m in reversed(messages):
            if m.__class__.__name__ == "AIMessage":
                from visvoai.cli.agent import chunk_text
                final = chunk_text(m).strip()
                if final:
                    break
        duration = _time.monotonic() - started
        summary = _telemetry_trailer(spec, dep_id, messages, duration)
        if run_registry is not None:
            run_registry.finish(dispatch_id, ok=bool(final), summary=summary,
                                final=final)
        elif trace_path is not None:
            _write_headless_trace(trace_path, spec, dispatch_id, task, dep_id,
                                  messages, summary)
        if not final:
            return f"ERROR: agent '{agent}' produced no final answer."
        return cap_lines(final, AGENT_RESULT_LINE_CAP) + "\n" + summary

    return StructuredTool.from_function(
        coroutine=_run_agent,
        name="run_agent",
        description=_roster_description(specs),
    )
