"""
visvoai.cli.context — CLI-specific runtime context.

CLIContext extends RuntimeContext with filesystem context for developer tool use.
No auth, no DB, no streaming queues — just the working directory and path constraints.
"""
from dataclasses import dataclass
from typing import List, Optional
from visvoai.core.context import RuntimeContext


@dataclass
class CLIContext(RuntimeContext):
    """
    CLI surface extension of RuntimeContext.

    Adds filesystem scope (cwd, allowed_paths) for the developer tool use case.
    Tools read self._context.cwd to resolve relative paths consistently.
    """
    cwd: str = "."
    # Optional whitelist of absolute path prefixes the agent is allowed to read/write.
    # None = no restriction (agent can access anything cwd can). Set to [cwd] for
    # safe operation when the user wants to constrain the agent to the project.
    allowed_paths: Optional[List[str]] = None
