"""
agent.py — the real visvoai-core pipeline behind the TUI (integration Phase 1).

Keeps all live-pipeline glue in one place so app.py only orchestrates widgets:
  - chat_models() / default_chat_model() : the model picker, driven by the registry
  - build_agent_graph()                  : provider (visvoai-ai) → CLIRuntime graph
  - chunk_text / tool_output_text / fmt_args : astream_events payload extractors

No private imports — a pure public-package consumer (visvoai-ai + visvoai-core).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from visvoai.ai import get_deployment

SYSTEM_PROMPT = (
    "You are a developer tool with access to the local filesystem and a shell.\n"
    "Help the developer with coding tasks: read files, edit code, run commands, "
    "explain what you find. Be precise and minimal. Always read a file before "
    "editing it. After changes, verify by reading back or running tests.\n"
    "For a SIMPLE relationship or flow (a few nodes, a linear or lightly-branched "
    "path), draw it inline as a compact arrow diagram (e.g. `parse -> validate -> "
    "store`) so it reads directly in the terminal — do not use mermaid for these. "
    "Reserve a fenced ```mermaid code block for genuinely COMPLEX diagrams (many "
    "nodes, real branching, or sequence/state/ER/class diagrams); the CLI renders "
    "those in the browser. Use that fence, not any other diagram syntax or HTML tag.\n"
    "Use web_search only when the answer depends on current, changing, or external "
    "information you don't already have — don't search for stable facts you can "
    "answer directly. Use web_fetch to read a specific URL you already have; use "
    "web_search (not web_fetch) when you don't have the URL yet."
)


def provider_has_key(provider_name: str) -> bool:
    """True if provider_name has a resolvable API key. Checks the {PROVIDER}_API_KEY
    convention first (covers models.dev providers not in the static key map — e.g.
    deepseek, nebius), then visvoai-ai's static resolution (gemini/anthropic/…)."""
    import os

    from visvoai.ai.providers.config import resolve_api_key
    from visvoai.cli.keys import env_var_for

    if os.environ.get(env_var_for(provider_name)):
        return True
    try:
        resolve_api_key(provider_name)
        return True
    except KeyError:
        return False


def chat_models(available_only: bool = False) -> List[Tuple[str, str]]:
    """(deployment_id, label) for selectable CHAT deployments in the registry.

    Excludes disabled/deprecated. With available_only=True, also excludes
    deployments whose provider has no API key configured — so the picker shows
    only what you can actually run. Label is provider + display name.
    """
    from visvoai.ai import list_deployments, Capability

    out: List[Tuple[str, str]] = []
    for d in list_deployments(Capability.CHAT):
        if available_only and not provider_has_key(d.provider):
            continue
        out.append((d.id, f"{d.provider} · {d.display_name}"))
    return out


@dataclass(frozen=True)
class DeployView:
    """UI-facing view of a chat deployment — the fields the model page + footer
    render. Keeps the screens off direct visvoai.ai imports."""
    id: str
    display_name: str
    provider: str
    family: str
    in_cost: float
    out_cost: float
    supports_thinking: bool
    thinking_levels: List[str]   # e.g. ["off", "low", "medium", "high"]
    default_thinking: str
    context_window: int          # max context tokens (0 = unknown → no gauge)
    connected: bool              # provider has a usable key right now

    @property
    def selectable_thinking(self) -> bool:
        """True when there's a real choice to make (more than one level)."""
        return self.supports_thinking and len(self.thinking_levels) > 1


def _to_view(info, connected: bool) -> "DeployView":
    return DeployView(
        id=info.id, display_name=info.display_name, provider=info.provider,
        family=info.family,
        in_cost=info.input_cost_per_million, out_cost=info.output_cost_per_million,
        supports_thinking=info.supports_thinking,
        thinking_levels=[lvl.value for lvl in info.thinking_levels],
        default_thinking=info.default_thinking.value,
        context_window=info.context_window,
        connected=connected,
    )


def turn_cost(deployment_id: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of a turn's token usage against the deployment's rate card (input +
    output only; cache/thinking refinements deferred). 0.0 on an unknown id."""
    from visvoai.ai import cost_of
    try:
        return cost_of(deployment_id, input_tokens, output_tokens)
    except Exception:
        return 0.0


def usage_of(message_or_chunk) -> dict:
    """{'input','output','total'} token counts from a message/chunk (0s if absent)."""
    from visvoai.ai import usage_from
    return usage_from(message_or_chunk)


def _baked_deployment_ids() -> set:
    """Composite ids of the curated baked deployments (~the hand-picked floor). These are
    always shown in the picker (connected or locked); a provider's broader models.dev
    catalog appears only when that provider is keyed — so abundance doesn't drown the list
    yet the curated set stays visible on a keyless install."""
    from visvoai.ai import BakedSource, Capability, DeploymentRegistry
    reg = DeploymentRegistry(BakedSource().models())
    return {info.id for info in reg.list_deployments(Capability.CHAT)}


def chat_deployments() -> List["DeployView"]:
    """Selectable CHAT deployments as DeployView, tagged connected/locked. Shows the
    curated baked deployments plus models.dev models for providers you have a key for.
    The model page groups + orders these (connected first)."""
    from visvoai.ai import Capability, list_deployments
    baked_ids = _baked_deployment_ids()
    out: List["DeployView"] = []
    for d in list_deployments(Capability.CHAT):
        keyed = provider_has_key(d.provider)
        if keyed or d.id in baked_ids:
            out.append(_to_view(d, keyed))
    return out


def deployment_view(deployment_id: str) -> "DeployView | None":
    """The DeployView for one deployment id (footer/startup), or None if unknown."""
    from visvoai.ai import get_deployment_info
    info = get_deployment_info(deployment_id)
    return _to_view(info, provider_has_key(info.provider)) if info else None


def default_chat_model() -> str:
    """Default deployment: the registry default if its provider is connected, else
    the first connected CHAT deployment, else the registry default (app still
    starts; the turn will prompt for a key)."""
    from visvoai.ai import default_deployment, Capability

    rd = default_deployment(Capability.CHAT)
    if rd is None:
        raise RuntimeError("model registry has no selectable CHAT deployment")
    dep = get_deployment(rd)
    if dep and provider_has_key(dep.provider):
        return rd
    connected = chat_models(available_only=True)
    return connected[0][0] if connected else rd


def api_key_available(deployment_id: str) -> bool:
    """True if the provider for deployment_id has a resolvable API key.

    Lets the UI fail fast with a clear message instead of building a graph and
    blocking on a doomed provider call — and keeps tests/headless runs from ever
    opening a real client when no key is configured.
    """
    dep = get_deployment(deployment_id)
    return provider_has_key(dep.provider if dep else "gemini")


def build_agent_graph(deployment_id: str, cwd: str, approve=None, level: str | None = None,
                      extra_tools: list | None = None, process_registry=None,
                      enable_agents: bool = True, agent_trace_dir_fn=None):
    """Resolve the deployment via visvoai-ai and build the CLIRuntime agent graph.

    level: the chosen thinking level ('off'|'low'|'medium'|'high'), or None to let
    build_chat_model apply the deployment's declared default_thinking. The model page
    lets the user pick a level; an unset level still falls back to the safe default.

    approve: optional async approve(tool_name, args)->bool gate. When given,
    mutating tools (edit/write/shell) require approval; when None, the ungated
    package tools are used. Raises (KeyError/ImportError/ValueError) on a missing
    key/integration/unknown deployment — the caller surfaces it in the UI.

    extra_tools: additional pre-built LangChain tools (e.g. discovered MCP tools)
    appended to the standard set. When approve is given they are gated too — an
    MCP tool is an external action, same trust tier as shell.

    process_registry: the app's ProcessRegistry. When given, the background tools
    (start/check/stop_process) are added. They gate THEMSELVES (start/stop only —
    check is a read), so they are not wrapped by gate_tool.

    enable_agents: adds the run_agent delegation tool (built-in + user-defined
    subagents). Not wrapped by gate_tool — dispatching is free; a subagent's own
    MUTATING tool calls still hit the same approve() gate. Subagent graphs are
    built without this flag, capping delegation depth at 1.
    """
    from visvoai.ai import build_chat_model
    from visvoai.cli.context import build_assembler
    from visvoai.cli.runtime import CLIRuntime
    from visvoai.cli.tools import build_cli_tools

    model = build_chat_model(deployment_id, level=level)

    if approve is not None:
        from visvoai.cli.gated_tools import build_gated_tools, gate_tool
        tools = build_gated_tools(cwd=cwd, approve=approve)
        tools += [gate_tool(t, approve) for t in (extra_tools or [])]
    else:
        tools = build_cli_tools(cwd=cwd) + list(extra_tools or [])
    if process_registry is not None:
        from visvoai.cli.tools.background import build_background_tools
        tools += build_background_tools(process_registry, cwd=cwd, approve=approve)
    if enable_agents:
        from visvoai.cli.agents import build_run_agent_tool
        tools.append(build_run_agent_tool(cwd=cwd, deployment_id=deployment_id,
                                          approve=approve, level=level,
                                          extra_tools=extra_tools,
                                          trace_dir_fn=agent_trace_dir_fn))
    assembler = build_assembler(SYSTEM_PROMPT, cwd)
    return CLIRuntime(assembler=assembler).build_graph(
        model=model,
        core_tools=tools,
        all_tools_map={t.name: t for t in tools},
        system_prompt=SYSTEM_PROMPT,
    )


# A cheap, fast deployment for the one-shot title summary. Falls back gracefully
# if it isn't in the registry.
_TITLE_DEPLOYMENT = "gemini:gemini-3.1-flash-lite"
_TITLE_PROMPT = (
    "Generate a terse 3–6 word title for a coding conversation that opens with the "
    "message below. Title case, no quotes, no trailing punctuation, no preamble — "
    "output ONLY the title."
)


async def generate_title(opening: str) -> Optional[str]:
    """One-shot cheap-LLM summary of the opening turn into a short title. Returns
    None when the provider has no key or the call fails — the caller keeps its
    first-prompt fallback. Never raises."""
    dep = get_deployment(_TITLE_DEPLOYMENT)
    if dep is None or not provider_has_key(dep.provider):
        return None
    try:
        from visvoai.ai import build_chat_model
        from langchain_core.messages import HumanMessage, SystemMessage

        model = build_chat_model(_TITLE_DEPLOYMENT, level="off")
        resp = await model.ainvoke(
            [SystemMessage(content=_TITLE_PROMPT), HumanMessage(content=opening[:2000])]
        )
        text = resp.content if isinstance(resp.content, str) else chunk_text(resp)
        title = " ".join(text.split()).strip().strip('"').strip("'")
        return title[:60] or None
    except Exception:
        return None


_COMPACT_PROMPT = (
    "You are compacting a coding assistant's conversation to save context. Summarize the "
    "transcript below into a dense hand-off note the assistant can continue from. Capture: "
    "the user's goal(s) and constraints; key decisions and why; files/functions touched and "
    "how; commands run and their outcomes; open threads and next steps. Preserve concrete "
    "names, paths, and values — omit chit-chat. Use terse bullet points. Output ONLY the note."
)


async def summarize_history(deployment_id: str, transcript: str) -> Optional[str]:
    """One-shot LLM summary of an earlier conversation slice into a dense continuation
    note (for /compact). Uses the active model. Returns None when its provider has no
    key or the call fails/yields nothing — the caller then leaves the thread untouched.
    Never raises."""
    dep = get_deployment(deployment_id)
    if dep is None or not provider_has_key(dep.provider):
        return None
    try:
        from visvoai.ai import build_chat_model
        from langchain_core.messages import HumanMessage, SystemMessage

        model = build_chat_model(deployment_id, level="off")
        resp = await model.ainvoke(
            [SystemMessage(content=_COMPACT_PROMPT), HumanMessage(content=transcript[:60_000])]
        )
        text = resp.content if isinstance(resp.content, str) else chunk_text(resp)
        return text.strip() or None
    except Exception:
        return None


def render_thread(messages) -> str:
    """A plain-text rendering of a message list for summarization: role-tagged turns,
    tool calls, and (capped) tool results. Not for display — for feeding a summarizer."""
    lines: list[str] = []
    for m in messages:
        kind = m.__class__.__name__
        if kind == "HumanMessage":
            lines.append(f"USER: {chunk_text(m).strip()}")
        elif kind == "AIMessage":
            t = chunk_text(m).strip()
            if t:
                lines.append(f"ASSISTANT: {t}")
            for tc in (getattr(m, "tool_calls", None) or []):
                lines.append(f"  ⮕ {tc.get('name', 'tool')}({fmt_args(tc.get('args') or {})})")
        elif kind == "ToolMessage":
            out = tool_output_text(m)
            lines.append(f"  TOOL RESULT: {out[:1000]}")
    return "\n".join(lines)


def classify_chunk(chunk: Any):
    """Yield (kind, text) for a stream chunk — kind in {'text', 'thinking'}.

    Mirrors the provider facade's content mapping: a chunk's content is a plain
    string (text) or a list of typed blocks ('text' vs 'thinking'/reasoning). The
    UI renders 'thinking' into the collapsible Thinking block and 'text' into the
    Assistant reply. Reasoning only arrives when the model has thinking enabled
    (the deployment's default_thinking, applied by build_chat_model)."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        if content:
            yield ("text", content)
        return
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict):
                bt = p.get("type")
                if bt == "thinking":
                    t = p.get("thinking") or p.get("thinking_delta") or ""
                    if t:
                        yield ("thinking", t)
                elif bt in (None, "text"):
                    t = p.get("text") or p.get("text_delta") or ""
                    if t:
                        yield ("text", t)
            elif isinstance(p, str) and p:
                yield ("text", p)


def thinking_text(message: Any) -> str:
    """Concatenated reasoning text from a message's content blocks (empty if none).
    Used on resume to rebuild the collapsed Thinking block from saved history."""
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return ""
    parts = []
    for p in content:
        if isinstance(p, dict) and p.get("type") == "thinking":
            parts.append(p.get("thinking") or p.get("thinking_delta") or "")
    return "".join(parts)


def chunk_text(chunk: Any) -> str:
    """Plain text from an on_chat_model_stream chunk (str content or list-of-parts)."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                # skip thinking parts here — those render as a Thinking block (Phase 4)
                if p.get("type") in (None, "text"):
                    parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    return ""


def tool_output_text(output: Any) -> str:
    """Plain text from an on_tool_end output (ToolMessage, str, or other)."""
    content = getattr(output, "content", output)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return str(content)


def fmt_args(tool_input: Any) -> str:
    """Compact one-line arg summary for a tool node target (e.g. 'api/main.py')."""
    if isinstance(tool_input, dict):
        if not tool_input:
            return ""
        # Prefer a single salient path-like value; else key=value pairs.
        if len(tool_input) == 1:
            return str(next(iter(tool_input.values())))
        return ", ".join(f"{k}={v}" for k, v in tool_input.items())
    return str(tool_input) if tool_input is not None else ""
