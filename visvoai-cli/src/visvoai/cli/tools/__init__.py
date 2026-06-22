"""
visvoai.cli.tools — Core developer tool CLI toolkit.

These tools are plain LangChain @tool decorated functions — no BaseAgentTool
dependency, no DB writes, no platform imports. They work with any surface that
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


@tool
def read_file(path: str) -> str:
    """Read the contents of a file at the given path. Returns the raw text."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.splitlines()
    # Return with line numbers so edits can be precise
    return "\n".join(f"{i+1}\t{line}" for i, line in enumerate(lines))


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it (and any parent directories) if needed."""
    abs_path = os.path.abspath(path)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} chars to {abs_path}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace the first occurrence of old_string with new_string in the file at path.

    Returns an error if old_string is not found or if it is ambiguous (appears more than once).
    """
    abs_path = os.path.abspath(path)
    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(old_string)
    if count == 0:
        return f"ERROR: old_string not found in {path}. No changes made."
    if count > 1:
        return (
            f"ERROR: old_string appears {count} times in {path} — cannot edit unambiguously. "
            "Provide more surrounding context to make the match unique."
        )
    new_content = content.replace(old_string, new_string, 1)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"Replaced in {abs_path}"


@tool
def list_files(path: str = ".") -> str:
    """List files and directories at path. Directories are marked with a trailing /."""
    abs_path = os.path.abspath(path)
    entries = sorted(os.listdir(abs_path))
    lines = []
    for entry in entries:
        full = os.path.join(abs_path, entry)
        lines.append(entry + ("/" if os.path.isdir(full) else ""))
    return "\n".join(lines) if lines else "(empty)"


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
    output += f"\n[exit: {result.returncode}]"
    return output.strip()


def build_cli_tools(cwd: Optional[str] = None) -> List[BaseTool]:
    """Return the standard CLI tool set. cwd is reserved for future path-scoping."""
    return [read_file, write_file, edit_file, list_files, run_shell]
