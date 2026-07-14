"""Plugin tools — drop this file in ~/.visvoai/tools/ and restart the CLI.

The contract (visvoai.cli.toolkit.make_cli_tool):
  · schema comes from your type hints, description from the docstring
  · output is capped; exceptions come back as "ERROR: …" data (a broken tool
    can never crash a turn)
  · gate is DECLARED per tool:  None (free — pure reads) · "approve" (the
    user confirms each call) · "self" (the function gates internally)
Global-only by design: a repo can never inject Python into your session.

Three tools below show the three shapes: sync read (ungated), sync action
(approve-gated), async (awaited on the UI loop — no threads needed).
"""
import asyncio
import subprocess

from visvoai.cli.toolkit import make_cli_tool


def git_authors(days: int = 30) -> str:
    """Who committed to this repo recently, with commit counts."""
    out = subprocess.run(
        ["git", "shortlog", "-sn", f"--since={days} days ago", "HEAD"],
        capture_output=True, text=True, timeout=10)
    return out.stdout or out.stderr


def tag_release(version: str, message: str = "") -> str:
    """Create an annotated git tag for a release (asks you first)."""
    out = subprocess.run(
        ["git", "tag", "-a", version, "-m", message or version],
        capture_output=True, text=True, timeout=10)
    return out.stderr or f"tagged {version}"


async def wait_for_port(port: int, seconds: int = 15) -> str:
    """Wait until a local TCP port accepts connections (e.g. a dev server)."""
    for _ in range(seconds * 2):
        try:
            _, w = await asyncio.open_connection("127.0.0.1", port)
            w.close()
            return f"port {port} is up"
        except OSError:
            await asyncio.sleep(0.5)
    return f"ERROR: port {port} not up after {seconds}s"


TOOLS = [
    make_cli_tool(git_authors, gate=None),        # read → runs silently
    make_cli_tool(tag_release, gate="approve"),   # mutates → you confirm
    make_cli_tool(wait_for_port, gate=None),      # async just works
]
