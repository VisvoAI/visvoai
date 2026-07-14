"""turn_events — THE SORTER: whose announcement is this?

One job: look at a stream event and route it. Sub-agent events (tagged
`visvoai_subagent:<name>:<dispatch>`) are the sub-agent's private execution —
they feed the run registry (side panel · /runs · trace) and the footer pulse,
and must NEVER reach the conversation or its persistence. Main events pass
through untouched for the conductor (agent_turn.py) to orchestrate.

Extracted verbatim from the turn loop's tagged branch in the C-split.
"""
from __future__ import annotations

from visvoai.cli import agent
from visvoai.cli.agents import subagent_key_from_tags


def route_subagent_event(app, event: dict, kind: str, data: dict) -> tuple[int, int] | None:
    """If `event` belongs to a sub-agent run: absorb it (registry steps +
    status pulse) and return the (input, output) token deltas its model chunks
    carried — real spend that counts toward the turn. Returns None for main
    events (the conductor handles those)."""
    sub_key = subagent_key_from_tags(event.get("tags"))
    if sub_key is None:
        return None
    sub_name, sub_dispatch = sub_key
    tin = tout = 0
    if kind == "on_chat_model_stream":
        u = agent.usage_of(data.get("chunk"))
        tin += u["input"]; tout += u["output"]
    elif kind == "on_tool_start":
        tname = event.get("name", "tool")
        app._set_status(f"agent {sub_name}: {tname}…")
        app._agent_runs.step_start(
            sub_dispatch, event.get("run_id", ""), tname,
            agent.fmt_args(data.get("input") or {})[:200])
    elif kind == "on_tool_end":
        out = agent.tool_output_text(data.get("output"))
        first = next((l for l in out.splitlines() if l.strip()), "")
        failed = first.startswith("ERROR") or "[exit: -1]" in out
        app._agent_runs.step_end(
            sub_dispatch, event.get("run_id", ""), first, not failed)
    elif kind == "on_tool_error":
        app._agent_runs.step_end(
            sub_dispatch, event.get("run_id", ""),
            str(data.get("error") or "tool error")[:200], False)
    return (tin, tout)
