"""
visvoai.core.runtime — AgentRuntime: extensible agent graph builder.

Usage:
  runtime = AgentRuntime()
  graph = runtime.build_graph(model, core_tools, all_tools_map, system_prompt)

Extend by subclassing:
  class MyRuntime(AgentRuntime):
      def _extend_graph(self, workflow, tool_configs):
          # add HITL node, background_task node, etc.

      def _tools_routing(self, tool_configs):
          def route(state): return "hitl" if state.get("needs_approval") else "agent"
          return route, {"hitl": "hitl", "agent": "agent"}

      def _get_checkpointer(self, checkpointer=None):
          return MyCheckpointer()

      def _get_interrupt_nodes(self):
          return ["hitl"]
"""
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph

from visvoai.core.state import AgentState
from visvoai.core.graph import build_graph as _core_build_graph


class AgentRuntime:
    """
    Extensible agent runtime — the public surface for building the agent graph.

    The default implementation produces the core agent→tools loop with no
    extra nodes. Override the hook methods to customize behavior:

      _extend_graph(workflow, tool_configs) — add nodes (HITL, bg_task, etc.)
      _build_agent_node(ctx)                — substitute the agent node
      _build_tools_node(ctx)                — substitute the tools node
      _agent_routing(ctx)                   — (fn, map) for the agent→X edge
      _tools_routing(tool_configs)          — (fn, map) for the tools→X edge
      _get_checkpointer(checkpointer)       — inject a checkpointer
      _get_interrupt_nodes()                — declare interrupt_before node names

    A richer consumer subclasses this to add its own nodes (e.g. an approval
    gate), a checkpointer, and interrupt points — all through the hooks above.
    """

    def build_graph(
        self,
        model: BaseChatModel,
        core_tools: List[Any],
        all_tools_map: Optional[Dict[str, Any]] = None,
        system_prompt: str = "",
        checkpointer: Optional[BaseCheckpointSaver] = None,
        tool_configs: Optional[Dict[str, Any]] = None,
        lean_prompt: bool = False,
        per_round_retrieve: Optional[Any] = None,
    ):
        """Build the compiled StateGraph with this runtime's hooks applied.

        Uses the core graph builder in visvoai.core.graph. A subclass may
        override this method entirely to call its own richer graph builder.
        """
        return _core_build_graph(
            model=model,
            core_tools=core_tools,
            all_tools_map=all_tools_map,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            tool_configs=tool_configs,
            lean_prompt=lean_prompt,
            per_round_retrieve=per_round_retrieve,
            _runtime=self,
        )

    def _extend_graph(self, workflow: StateGraph, tool_configs: dict) -> None:
        """Add extra nodes and edges before compilation. Override in subclasses."""
        pass

    def _build_agent_node(self, ctx):
        """Return the node placed at 'agent', or None to use the core default.

        ctx is a GraphBuildContext (model, tools, system_prompt, retrieval, …).
        Override to supply a richer agent node (custom prompt assembly, message
        pre/post-processing) built from the same inputs, without re-implementing
        build_graph. Default None → core's call_model (retrieval + step-budget).
        """
        return None

    def _build_tools_node(self, ctx):
        """Return the node placed at 'tools', or None to use the core default.

        ctx is a GraphBuildContext. Override to substitute a custom tools node
        (e.g. one that gates execution behind an approval step). Default None →
        ToolNode(ctx.all_tools).
        """
        return None

    def _agent_routing(self, ctx):
        """Return (routing_fn, routing_map) for the agent→X edge, or None for the default.

        ctx is a GraphBuildContext. Override to route the agent node somewhere
        other than {tools, END} (e.g. through a finalize-check node). Default None
        → core's should_continue with {"tools": "tools", END: END}.
        """
        return None

    def _tools_routing(self, tool_configs: dict):
        """Return (routing_fn, routing_map) for the tools→X conditional edge.

        Default: always routes back to agent (no interrupt nodes).
        """
        def _route(state: AgentState) -> str:
            return "agent"
        return _route, {"agent": "agent"}

    def _get_checkpointer(
        self, checkpointer: Optional[BaseCheckpointSaver] = None
    ) -> Optional[BaseCheckpointSaver]:
        """Return the checkpointer to use. Default: pass through the provided value."""
        return checkpointer

    def _get_state_class(self) -> type:
        """The graph's state schema. Override to extend AgentState (TypedDict
        inheritance) with your own fields — they then flow through the graph
        alongside messages, without overriding build_graph."""
        from visvoai.core.state import AgentState
        return AgentState

    def _get_interrupt_nodes(self) -> Optional[List[str]]:
        """Return interrupt_before node names. Default: None (no interrupts)."""
        return None
