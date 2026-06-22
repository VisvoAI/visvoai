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
          return MyPostgresCheckpointer()

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
    platform-specific nodes. Override the hook methods to customize behavior:

      _extend_graph(workflow, tool_configs) — add nodes (HITL, bg_task, etc.)
      _tools_routing(tool_configs)          — (fn, map) for the tools→X edge
      _get_checkpointer(checkpointer)       — inject a checkpointer
      _get_interrupt_nodes()                — declare interrupt_before node names

    The private platform implements VisvoRuntime(AgentRuntime), which adds HITL,
    background_task nodes, a PostgreSQL checkpointer, and interrupt gates.
    """

    def build_graph(
        self,
        model: BaseChatModel,
        core_tools: List[BaseTool],
        all_tools_map: Dict[str, BaseTool],
        system_prompt: str,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        tool_configs: Optional[Dict[str, Any]] = None,
        plan_state_ref: Optional[Dict[str, Any]] = None,
        lean_prompt: bool = False,
        per_round_retrieve: Optional[Any] = None,
    ):
        """Build the compiled StateGraph with this runtime's hooks applied.

        Uses the core graph builder in visvoai.core.graph. Platform subclasses
        (VisvoRuntime) override this method to call the richer backend graph builder
        that adds HITL, background tasks, and Plan-A retrieval.
        """
        return _core_build_graph(
            model=model,
            core_tools=core_tools,
            all_tools_map=all_tools_map,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            tool_configs=tool_configs,
            plan_state_ref=plan_state_ref,
            lean_prompt=lean_prompt,
            per_round_retrieve=per_round_retrieve,
            _runtime=self,
        )

    def _extend_graph(self, workflow: StateGraph, tool_configs: dict) -> None:
        """Add extra nodes and edges before compilation. Override in subclasses."""
        pass

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

    def _get_interrupt_nodes(self) -> Optional[List[str]]:
        """Return interrupt_before node names. Default: None (no interrupts)."""
        return None
