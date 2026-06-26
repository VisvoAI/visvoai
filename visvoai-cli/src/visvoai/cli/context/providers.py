"""
visvoai.cli.context.providers — the v1 context providers.

Five providers, locked for v1:
  base_prompt          (static)   — the agent's standing system prompt
  project_instructions (static)   — nearest AGENTS.md files up from cwd
  environment          (static)   — OS / cwd / shell
  datetime             (per_turn) — current UTC date/time (kept out of the prefix)
  git_state            (per_turn) — branch + ahead/behind + dirty paths

cwd-dependent providers receive cwd at construction (GraphBuildContext carries no
cwd). Every render() is defensive: it returns None rather than raising, so a
failure (no git, unreadable file) simply omits the section.
"""
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import List, Optional

from .protocol import ContextProvider

# Instruction-file names discovered while walking up from cwd, in priority order.
_INSTRUCTION_FILENAMES = ("AGENTS.md", "CLAUDE.md")
# Bound the walk and the bytes read so a deep tree or a huge file can't blow the budget.
_MAX_WALK_DEPTH = 6
_MAX_FILE_BYTES = 16_000
_MAX_DIRTY_FILES = 40


class BasePromptProvider(ContextProvider):
    """The standing system prompt — the stable core of the cacheable prefix."""

    name = "base_prompt"
    cadence = "static"
    default_order = 0
    default_budget_tokens = 4000

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def render(self, state: dict) -> Optional[str]:
        return self._prompt or None


class ProjectInstructionsProvider(ContextProvider):
    """AGENTS.md / CLAUDE.md instruction files found walking up from cwd.

    Nearest-first wins on filename collisions within a directory; the root of the
    walk is the first directory that has a `.git`, else the depth cap. Files are
    emitted nearest-to-farthest so the most specific guidance reads first."""

    name = "project_instructions"
    cadence = "static"
    default_order = 10
    default_budget_tokens = 3000

    def __init__(self, cwd: str) -> None:
        super().__init__()
        self._cwd = cwd

    def _discover(self) -> List[tuple[str, str]]:
        found: List[tuple[str, str]] = []
        d = os.path.abspath(self._cwd)
        for _ in range(_MAX_WALK_DEPTH):
            for fname in _INSTRUCTION_FILENAMES:
                path = os.path.join(d, fname)
                if os.path.isfile(path):
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as fh:
                            text = fh.read(_MAX_FILE_BYTES)
                    except OSError:
                        continue
                    if text.strip():
                        found.append((path, text.strip()))
                    break  # one instruction file per directory (priority order)
            if os.path.isdir(os.path.join(d, ".git")):
                break  # repo root — stop walking up
            parent = os.path.dirname(d)
            if parent == d:
                break  # filesystem root
            d = parent
        return found

    def render(self, state: dict) -> Optional[str]:
        files = self._discover()
        if not files:
            return None
        blocks = [f"### {os.path.basename(p)} ({p})\n{text}" for p, text in files]
        return "## Project instructions\n\n" + "\n\n".join(blocks)


class EnvironmentProvider(ContextProvider):
    """OS / working directory / shell — the static environment the agent runs in."""

    name = "environment"
    cadence = "static"
    default_order = 20
    default_budget_tokens = 200

    def __init__(self, cwd: str) -> None:
        super().__init__()
        self._cwd = cwd

    def render(self, state: dict) -> Optional[str]:
        shell = os.environ.get("SHELL", "") or "unknown"
        return (
            "## Environment\n"
            f"- OS: {platform.system()} {platform.release()}\n"
            f"- Working directory: {self._cwd}\n"
            f"- Shell: {shell}"
        )


class DateTimeProvider(ContextProvider):
    """Current UTC date/time — per_turn so it stays OUT of the cacheable prefix."""

    name = "datetime"
    cadence = "per_turn"
    default_order = 100
    default_budget_tokens = 50

    def render(self, state: dict) -> Optional[str]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        return f"**Current date/time (UTC):** {now}"


class GitStateProvider(ContextProvider):
    """Branch + ahead/behind + dirty paths. per_turn — the tree changes as the
    agent edits files within a turn. Diff-free (uses gitio.status_summary)."""

    name = "git_state"
    cadence = "per_turn"
    default_order = 110
    default_budget_tokens = 800

    def __init__(self, cwd: str) -> None:
        super().__init__()
        self._cwd = cwd

    def render(self, state: dict) -> Optional[str]:
        from visvoai.cli import gitio

        status = gitio.status_summary(self._cwd)
        if status is None:
            return None  # not a git repo

        head = f"## Git\n- Branch: {status['branch']}"
        if status.get("upstream") and (status.get("ahead") or status.get("behind")):
            head += f" (ahead {status['ahead'] or 0}, behind {status['behind'] or 0})"

        files = status.get("files", [])
        if not files:
            return head + "\n- Working tree: clean"

        shown = files[:_MAX_DIRTY_FILES]
        lines = [f"  {f['state']} {f['path']}" for f in shown]
        more = len(files) - len(shown)
        if more > 0:
            lines.append(f"  … and {more} more")
        return head + f"\n- Dirty files ({len(files)}):\n" + "\n".join(lines)
