"""
toolkit — the PUBLIC tool contract: make_cli_tool + the global .py tool loader.

make_cli_tool wraps a plain function into a CLI tool that follows the house
rules without the author writing them:
  · output capped (one call can't flood context)
  · exceptions become "ERROR: …" strings (data, never a raise — turns survive)
  · description cleandoc'd (the model reads it verbatim)
  · gate DECLARED as metadata — the graph builders read tool.metadata["gate"]
    instead of tribal knowledge about which tools self-gate:
       "approve" → wrapped with the user gate in gated mode
       "self"    → gates itself internally (passed through)
       None      → free (pure reads)

User plugin tools — GLOBAL ONLY, by design:
  ~/.visvoai/tools/*.py  →  module-level `TOOLS = [make_cli_tool(fn, …), …]`
Importing a .py is code execution inside the CLI process, so only files the
USER authored are ever imported. Project-layer python is deliberately
unsupported here (a cloned repo must never execute at startup) — projects get
declarative TOML tools / MCP servers instead.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
from typing import Callable, Literal, Optional

from langchain_core.tools import BaseTool, StructuredTool

from visvoai.cli.tools._common import cap_lines

logger = logging.getLogger(__name__)

DEFAULT_CAP = 1000
Gate = Optional[Literal["approve", "self"]]


def make_cli_tool(fn: Callable, *, gate: Gate = "approve",
                  cap: int = DEFAULT_CAP, name: str | None = None) -> BaseTool:
    """Wrap `fn` (sync or async; docstring = model-facing description; type
    hints = arg schema) into a house-rules CLI tool."""
    tool_name = name or fn.__name__

    if asyncio.iscoroutinefunction(fn):
        async def runner(**kwargs):
            try:
                out = await fn(**kwargs)
            except Exception as e:
                return f"ERROR: {e}"
            return cap_lines(str(out), cap)
        t = StructuredTool.from_function(coroutine=runner, name=tool_name,
                                         description=fn.__doc__ or tool_name,
                                         args_schema=None, infer_schema=True,
                                         parse_docstring=False)
    else:
        def runner(**kwargs):
            try:
                out = fn(**kwargs)
            except Exception as e:
                return f"ERROR: {e}"
            return cap_lines(str(out), cap)
        t = StructuredTool.from_function(func=runner, name=tool_name,
                                         description=fn.__doc__ or tool_name,
                                         args_schema=None, infer_schema=True,
                                         parse_docstring=False)
    # Schema must come from the AUTHOR's signature, not the **kwargs runner.
    from langchain_core.tools import create_schema_from_function
    t.args_schema = create_schema_from_function(tool_name, fn)
    t.description = inspect.cleandoc(t.description)
    t.metadata = {**(t.metadata or {}), "gate": gate}
    return t


def user_tools_dir():
    from visvoai.cli.store import visvoai_home
    return visvoai_home() / "tools"


def load_user_tools() -> list[BaseTool]:
    """Import every ~/.visvoai/tools/*.py and collect its `TOOLS` list.
    Global-only and user-authored — imported code runs in-process. A broken
    plugin is logged and skipped; it must never break the session."""
    root = user_tools_dir()
    if not root.is_dir():
        return []
    out: list[BaseTool] = []
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"visvoai_user_tools_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tools = getattr(mod, "TOOLS", None)
            if not isinstance(tools, list):
                logger.warning("toolkit: %s has no TOOLS list — skipped", path)
                continue
            for t in tools:
                if isinstance(t, BaseTool):
                    out.append(t)
                else:
                    logger.warning("toolkit: %s: non-tool entry in TOOLS "
                                   "(use make_cli_tool) — skipped", path)
        except Exception as e:
            logger.warning("toolkit: failed to load %s: %s", path, e)
    return out


def apply_gates(tools: list[BaseTool], approve) -> list[BaseTool]:
    """Wire declared gates: gate='approve' tools get wrapped with the user gate
    (when one is active); 'self'/None pass through. THE reader of the gate
    metadata — graph builders call this instead of knowing tools' habits."""
    from visvoai.cli.gated_tools import gate_tool

    out = []
    for t in tools:
        gate = (t.metadata or {}).get("gate")
        if gate == "approve" and approve is not None:
            out.append(gate_tool(t, approve))
        else:
            out.append(t)
    return out
