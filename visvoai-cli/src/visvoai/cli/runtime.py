"""
visvoai.cli.runtime — CLIRuntime: AgentRuntime for the developer tool CLI.

No interrupt nodes, no HITL, no background tasks — the CLI is synchronous and the
human is already in the loop. The base agent→tools→agent loop is exactly right.

The one override is the agent node: when constructed with a ContextAssembler,
CLIRuntime replaces the core's static-prompt call_model with one that assembles
the system prompt per turn (project instructions, git state, etc.). Without an
assembler it falls straight back to the core default — older callers and tests
that do `CLIRuntime()` are unaffected.
"""
from typing import Optional

from langchain_core.messages import SystemMessage

from visvoai.core.runtime import AgentRuntime

from .context import ContextAssembler
from .context.assembler import rounds_this_turn


class CLIRuntime(AgentRuntime):
    """Agent runtime for the CLI surface.

    With no assembler: the default AgentRuntime behaviour (core call_model, no
    checkpointer, no interrupts). With an assembler: a per-turn context-assembling
    agent node that still honours the soft step cap's forced-finalize.
    """

    def __init__(self, assembler: Optional[ContextAssembler] = None) -> None:
        self._assembler = assembler

    def _build_agent_node(self, ctx):
        # No assembler → core default (call_model reads ctx.system_prompt).
        if self._assembler is None:
            return None

        model = ctx.model
        all_tools = ctx.all_tools
        max_steps = ctx.max_agent_steps
        # The CLI has no deferrable/MCP tools and no per-round retrieval, so binding
        # is the simple bind-everything case — done once here.
        bound_model = model.bind_tools(all_tools) if all_tools else model
        assembler = self._assembler

        async def call_model(state: dict):
            messages = list(state.get("messages", []))

            # Soft step cap: at the ceiling, assemble with the finalize instruction
            # and invoke the UNBOUND model so no further tool calls are possible —
            # the user gets one clean final answer instead of hitting the hard limit.
            force_final = max_steps is not None and rounds_this_turn(messages) >= max_steps

            system = assembler.assemble(state, finalize=force_final)
            invoke_messages = (
                [SystemMessage(content=system), *messages] if system else messages
            )
            response = await (model if force_final else bound_model).ainvoke(invoke_messages)
            return {"messages": [response]}

        return call_model
