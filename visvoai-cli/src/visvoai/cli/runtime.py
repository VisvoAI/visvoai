"""
visvoai.cli.runtime — CLIRuntime: AgentRuntime for the developer tool CLI.

No interrupt nodes, no HITL, no background tasks — the CLI is synchronous and
the human is already in the loop. Extend AgentRuntime with no overrides needed:
the base class default (agent→tools→agent loop, no checkpointer) is exactly right.
"""
from visvoai.core.runtime import AgentRuntime


class CLIRuntime(AgentRuntime):
    """
    Agent runtime for the CLI surface.

    Uses the default AgentRuntime behavior:
      - No interrupt nodes (synchronous, human is in the loop)
      - No checkpointer (no cross-turn state persistence)
      - Default tools routing: always returns to agent after tool calls

    Override _extend_graph() to add nodes for more advanced CLI behavior
    (e.g. a confirmation prompt before destructive operations).
    """
    pass
