"""
visvoai.cli.tools — Core developer tool CLI toolkit.

These tools are plain LangChain @tool decorated functions — no BaseAgentTool
dependency, no datastore, pure local operations. They work with any surface that
accepts LangChain BaseTool instances.

Available tools:
  read_file   — read file contents
  write_file  — write/create a file
  edit_file   — exact string replacement in a file
  list_files  — list directory contents
  run_shell   — run a shell command (30s timeout)

Usage:
  from visvoai.cli.tools import build_cli_tools
  tools = build_cli_tools(cwd="/path/to/project")
"""
import os
import subprocess
from typing import List, Optional

from langchain_core.tools import BaseTool, tool

# Bounds that keep a single tool result from flooding the model's context (and the
# per-turn token cost). Reads page with offset/limit; list/shell output is capped
# with a clear "N more" marker so the model knows the result was clipped.
READ_LINE_CAP = 2000     # max lines returned per read_file call
MAX_LINE_LEN = 2000      # over-long lines are clipped (one line ≠ a whole file)
LIST_CAP = 1000          # max entries from list_files
SHELL_LINE_CAP = 1000    # max output lines from run_shell


def _clip_line(s: str) -> str:
    return s if len(s) <= MAX_LINE_LEN else s[:MAX_LINE_LEN] + " …[line truncated]"


def cap_lines(text: str, max_lines: int) -> str:
    """Return text limited to max_lines, with a marker noting how many were dropped."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + (
        f"\n…[output truncated: showing {max_lines} of {len(lines)} lines]")


@tool
def read_file(path: str, offset: int = 1, limit: int = READ_LINE_CAP) -> str:
    """Read a file as numbered lines. For large files this is paginated: it returns
    at most `limit` lines (capped at 2000) starting at the 1-based `offset`, and a
    trailing note tells you the total and how to page (raise `offset`). Over-long
    lines are clipped. Use this to read a window of a big file rather than all of it.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.read().splitlines()
    except OSError as e:
        # Report the failure as data so the agent can recover (retry, try another
        # path) — a raised exception would instead abort the whole turn.
        return f"ERROR: {e}"
    total = len(all_lines)
    if total == 0:
        return "(empty file)"
    start = max(1, offset)
    if start > total:
        return f"ERROR: offset {start} is past end of file ({total} lines)."
    limit = max(1, min(limit, READ_LINE_CAP))
    window = all_lines[start - 1: start - 1 + limit]
    end = start - 1 + len(window)
    body = "\n".join(f"{start + i}\t{_clip_line(ln)}" for i, ln in enumerate(window))
    if start > 1 or end < total:
        remaining = total - end
        note = f"[lines {start}–{end} of {total}"
        if remaining > 0:
            note += f"; {remaining} more — re-read with offset={end + 1}"
        note += "]"
        body += f"\n{note}"
    return body


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it (and any parent directories) if needed."""
    abs_path = os.path.abspath(path)
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
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace the first occurrence of old_string with new_string in the file at path.

    Returns an error if old_string is not found or if it is ambiguous (appears more than once).
    """
    abs_path = os.path.abspath(path)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return f"ERROR: {e}"
    count = content.count(old_string)
    if count == 0:
        return f"ERROR: old_string not found in {path}. No changes made."
    if count > 1:
        return (
            f"ERROR: old_string appears {count} times in {path} — cannot edit unambiguously. "
            "Provide more surrounding context to make the match unique."
        )
    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        return f"ERROR: {e}"
    return f"Replaced in {abs_path}"


@tool
def list_files(path: str = ".") -> str:
    """List files and directories at path. Directories are marked with a trailing /."""
    abs_path = os.path.abspath(path)
    try:
        entries = sorted(os.listdir(abs_path))
    except OSError as e:
        return f"ERROR: {e}"
    lines = []
    for entry in entries:
        full = os.path.join(abs_path, entry)
        lines.append(entry + ("/" if os.path.isdir(full) else ""))
    return cap_lines("\n".join(lines), LIST_CAP) if lines else "(empty)"


@tool
def run_shell(command: str) -> str:
    """Run a shell command and return its combined stdout + stderr output.

    Timeout: 30 seconds. Working directory: the cwd this CLI was launched from.
    Returns the output followed by the exit code.
    """
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    # Cap the body first, then append the exit marker so it survives truncation
    # (the UI parses '[exit: N]' to decide success/failure).
    output = cap_lines(output.strip(), SHELL_LINE_CAP)
    return f"{output}\n[exit: {result.returncode}]".strip()


def build_cli_tools(cwd: Optional[str] = None) -> List[BaseTool]:
    """Return the standard CLI tool set. cwd is reserved for future path-scoping."""
    return [read_file, write_file, edit_file, list_files, run_shell]
