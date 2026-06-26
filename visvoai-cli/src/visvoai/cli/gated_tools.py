"""
gated_tools.py — CLI tools with a permission gate on mutating operations.

read_file / list_files are reused from the package unchanged (read-only, never
gated). edit_file / write_file / run_shell are ASYNC and await an injected
approve(tool_name, args) -> bool callback BEFORE mutating — the app shows the
inline approval HITL and resolves it. (Phase-0 proved async tools run on the UI
event loop, so the callback is a plain await — no thread bridge.) shell runs in
a worker thread so the UI stays responsive.

Denied calls return a plain message to the model (no mutation), so the agent can
adapt instead of erroring.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import subprocess
from typing import Awaitable, Callable, List

from langchain_core.tools import BaseTool, tool

from visvoai.cli.tools import (   # read-only tools reused as-is; caps shared
    list_files, list_tree, read_file, web_search, web_fetch, cap_lines, SHELL_LINE_CAP,
)

ApproveFn = Callable[[str, dict], Awaitable[bool]]

_DENIED = "User declined this action. No changes were made — adjust the plan or ask why."


def build_gated_tools(cwd: str, approve: ApproveFn) -> List[BaseTool]:
    """Tool set where edit/write/shell await `approve` before any mutation, and
    edit/write are path-confined to `cwd` (+ configured extra roots)."""
    from visvoai.cli.pathguard import PathDenied, confine, resolve_roots

    roots = resolve_roots(cwd)

    @tool
    async def edit_file(path: str, old_string: str, new_string: str) -> str:
        """Replace the first occurrence of old_string with new_string in the file at path.
        Errors if old_string is missing or appears more than once."""
        try:
            abs_path = confine(path, roots)   # boundary first — never prompt for an out-of-root path
        except PathDenied as e:
            return f"ERROR: {e}"
        if not await approve("edit_file", {"path": path, "old_string": old_string,
                                           "new_string": new_string}):
            return _DENIED
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return f"ERROR: {e}"   # report as data so the agent can recover
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {path}. No changes made."
        if count > 1:
            return (f"ERROR: old_string appears {count} times in {path} — cannot edit "
                    "unambiguously. Provide more surrounding context.")
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content.replace(old_string, new_string, 1))
        except OSError as e:
            return f"ERROR: {e}"
        return f"Replaced in {abs_path}"

    @tool
    async def write_file(path: str, content: str) -> str:
        """Write content to a file, creating it (and parent dirs) if needed."""
        try:
            abs_path = confine(path, roots)   # boundary first — never prompt for an out-of-root path
        except PathDenied as e:
            return f"ERROR: {e}"
        if not await approve("write_file", {"path": path, "content": content}):
            return _DENIED
        try:
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"ERROR: {e}"
        return f"Wrote {len(content)} chars to {abs_path}"

    @tool
    async def run_shell(command: str) -> str:
        """Run a shell command (30s timeout) and return combined output + exit code.

        Full shell syntax works (pipes, &&, redirects). Filter NOISY output inline
        when you only need part of it (`… 2>&1 | grep -E "FAIL|Error"`, `… | tail
        -40`) — but don't over-filter: if the whole result matters or a failure's
        cause could be anywhere, run it plain (output is capped automatically)."""
        if not await approve("run_shell", {"command": command}):
            return _DENIED
        result = await asyncio.to_thread(  # don't block the UI loop on the subprocess
            subprocess.run, command,
            shell=True, capture_output=True, text=True, timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        # Cap before the exit marker so '[exit: N]' (parsed by the UI) survives.
        output = cap_lines(output.strip(), SHELL_LINE_CAP)
        return f"{output}\n[exit: {result.returncode}]".strip()

    # Dedent the locally-defined tools' docstrings (the model sees them verbatim);
    # the imported read/list tools were already cleaned in the package.
    for t in (edit_file, write_file, run_shell):
        t.description = inspect.cleandoc(t.description)
    return [read_file, list_files, list_tree, edit_file, write_file, run_shell,
            web_search, web_fetch]
