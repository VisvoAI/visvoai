"""Shell tool: run_shell — a synchronous (30s) command runner with capped output."""
import subprocess

from langchain_core.tools import tool

from visvoai.cli.tools._common import as_text, cap_lines

SHELL_LINE_CAP = 1000    # max output lines from run_shell


SHELL_TIMEOUT_DEFAULT = 30   # seconds
SHELL_TIMEOUT_MAX = 600      # hard ceiling — synchronous, blocks the turn while running


@tool
def run_shell(command: str, timeout_seconds: int = SHELL_TIMEOUT_DEFAULT) -> str:
    """Run a shell command and return its combined stdout + stderr output.

    Full shell syntax works (pipes, &&/||, redirects). When you expect NOISY output
    but only care about part of it, filter inline — e.g. `pytest 2>&1 | grep -E
    "FAIL|Error"` or `npm run build 2>&1 | tail -40`. Don't over-filter, though: if
    you need to see the whole result (a short command, or a failure whose cause
    could be anywhere), run it plain — output is capped automatically, so a grep
    that hides the real error is worse than the cap.

    timeout_seconds: how long to wait before killing the command (default 30, max
    600). Raise it for known-slow commands (installs, builds, full test suites);
    keep it low for quick checks. Synchronous — not for long-running servers/watchers.

    Backgrounding (`cmd &`) a process that keeps writing to stdout will HANG this
    call until timeout — the pipe never closes. If you must background something,
    detach its output: `nohup cmd > /tmp/x.log 2>&1 & disown`, then read the log
    file. Prefer not to leave processes running: stop them when you're done.

    Working directory: the cwd this CLI was launched from. Output is followed by the
    exit code.
    """
    timeout = max(1, min(int(timeout_seconds or SHELL_TIMEOUT_DEFAULT), SHELL_TIMEOUT_MAX))
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        # A timeout is a TOOL error, not a turn-crashing exception: return it as data
        # (with the failure marker the UI parses) so the agent can adapt and the turn
        # survives. Include any partial output captured before the kill.
        out, err = as_text(e.stdout), as_text(e.stderr)
        partial = cap_lines(
            (out + (f"\n[stderr]\n{err}" if err else "")).strip(),
            SHELL_LINE_CAP)
        head = f"{partial}\n" if partial else ""
        return (f"{head}ERROR: command timed out after {timeout}s and was killed. "
                f"Pass a larger timeout_seconds (max {SHELL_TIMEOUT_MAX}) if it needs longer."
                f"\n[exit: -1]").strip()
    except Exception as e:  # any spawn/decoding failure is the tool's, not the turn's
        return f"ERROR: {e}\n[exit: -1]".strip()
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    # Cap the body first, then append the exit marker so it survives truncation
    # (the UI parses '[exit: N]' to decide success/failure).
    output = cap_lines(output.strip(), SHELL_LINE_CAP)
    return f"{output}\n[exit: {result.returncode}]".strip()
