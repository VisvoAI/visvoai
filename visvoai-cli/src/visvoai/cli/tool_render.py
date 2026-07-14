"""tool_render — THE PAINTER: a finished tool call → what you see.

Pure appearance, one job: given "tool X finished with result Y", pick the
Style-B body (edit→diff, write→content, shell→output+exit, agent→result card,
reads→plain output) and set the row's rail/status. No saving, no checkpoints,
no event knowledge — those live in the conductor (agent_turn.py).

Extracted verbatim from agent_turn._render_tool_result in the C-split; new
tool kinds (artifacts…) add a branch HERE, never inside the turn loop.
Returns True when the result was a failure (the conductor tracks that for
post-turn nudges).
"""
from __future__ import annotations

import re

from visvoai.cli.widgets import CleanDiff, ToolOutput


async def render_tool_result(node, name: str, args, output: str) -> bool:
    """Render a finished tool call into the right Style-B body, by tool type.
    edit/write bodies come from the INPUT args (the tools return only a
    confirmation string). Returns True if this result was a failure."""
    args = args if isinstance(args, dict) else {}

    if name == "edit_file":
        if output.startswith("ERROR"):
            node.set_rail("failed")
            await node.set_failure("", output)
            return True
        changes = ([("del", ln) for ln in args.get("old_string", "").splitlines()]
                   + [("add", ln) for ln in args.get("new_string", "").splitlines()])
        adds = sum(1 for k, _ in changes if k == "add")
        dels = sum(1 for k, _ in changes if k == "del")
        node.set_rail(f"+{adds} −{dels}")
        await node.set_body(CleanDiff(args.get("path", ""), changes), collapsed=True)
        node.set_status("complete")
        return False

    if name == "write_file":
        if output.startswith("ERROR"):
            node.set_rail("failed")
            await node.set_failure("", output)
            return True
        lines = (args.get("content", "") or "").splitlines() or [""]
        node.set_rail(f"{len(lines)} lines")
        await node.set_body(ToolOutput(lines), collapsed=True)
        node.set_status("complete")
        return False

    if name == "run_agent":
        # Lifecycle (registry finish) is the run_agent tool's job — this is
        # pure rendering: trailer → rail, report → collapsed body.
        a_name = str(args.get("agent", "?"))
        if output.startswith("ERROR"):
            node.set_rail("failed")
            await node.set_failure("", output)
            return True
        lines = output.splitlines()
        trailer = lines[-1] if lines and lines[-1].startswith("[agent:") else ""
        body_lines = lines[:-1] if trailer else lines
        rail = trailer.strip("[]").removeprefix(f"agent: {a_name} · ") if trailer else ""
        node.set_rail(rail or f"{len(body_lines)} lines")
        await node.set_body(ToolOutput(body_lines or [""]), collapsed=True)
        node.set_status("complete")
        return False

    if name == "run_shell":
        m = re.search(r"\[exit:\s*(-?\d+)\]", output)
        exit_code = int(m.group(1)) if m else 0
        if exit_code != 0:
            node.set_rail(f"exit {exit_code}")
            await node.set_failure(output, f"exit {exit_code}")
            return False   # non-zero exit renders as failure but never
                           # counted toward _turn_had_error before the split
        node.set_rail("exit 0")
        await node.set_body(ToolOutput(output.splitlines() or [""]), collapsed=True)
        node.set_status("complete")
        return False

    # read_file / list_files / unknown → plain output (or a reported error)
    if output.startswith("ERROR"):
        node.set_rail("failed")
        await node.set_failure("", output)
        return False       # matches pre-split behavior: generic errors don't
                           # set _turn_had_error
    lines = output.splitlines() or [""]
    noun = {"list_files": "items", "list_tree": "entries"}.get(name, "lines")
    node.set_rail(f"{len(lines)} {noun}")
    await node.set_body(ToolOutput(lines), collapsed=True)   # collapsed; click to expand
    node.set_status("complete")
    return False
