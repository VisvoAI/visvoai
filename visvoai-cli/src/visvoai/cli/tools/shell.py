"""Shell tool: run_shell — a synchronous (30s) command runner with capped output."""
import subprocess

from langchain_core.tools import tool

from visvoai.cli.tools._common import cap_lines

SHELL_LINE_CAP = 1000    # max output lines from run_shell


@tool
def run_shell(command: str) -> str:
    """Run a shell command and return its combined stdout + stderr output.

    Full shell syntax works (pipes, &&/||, redirects). When you expect NOISY output
    but only care about part of it, filter inline — e.g. `pytest 2>&1 | grep -E
    "FAIL|Error"` or `npm run build 2>&1 | tail -40`. Don't over-filter, though: if
    you need to see the whole result (a short command, or a failure whose cause
    could be anywhere), run it plain — output is capped automatically, so a grep
    that hides the real error is worse than the cap.

    Timeout: 30 seconds (synchronous — not for long-running servers/watchers).
    Working directory: the cwd this CLI was launched from. Output is followed by the
    exit code.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        # A timeout is a TOOL error, not a turn-crashing exception: return it as data
        # (with the failure marker the UI parses) so the agent can adapt and the turn
        # survives. Include any partial output captured before the kill.
        partial = cap_lines(
            ((e.stdout or "") + (f"\n[stderr]\n{e.stderr}" if e.stderr else "")).strip(),
            SHELL_LINE_CAP)
        head = f"{partial}\n" if partial else ""
        return f"{head}ERROR: command timed out after 30s and was killed.\n[exit: -1]".strip()
    except Exception as e:  # any spawn/decoding failure is the tool's, not the turn's
        return f"ERROR: {e}\n[exit: -1]".strip()
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    # Cap the body first, then append the exit marker so it survives truncation
    # (the UI parses '[exit: N]' to decide success/failure).
    output = cap_lines(output.strip(), SHELL_LINE_CAP)
    return f"{output}\n[exit: {result.returncode}]".strip()
