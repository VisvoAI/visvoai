"""Tool intake normalization — write tools your way, the loop takes them all.

`build_graph` (and anything else that consumes tools) accepts, per tool:

  1. a plain typed Python function (sync or async) — schema from type hints,
     description from the docstring; no framework imports in your file
  2. a `BaseAgentTool` subclass or instance — the lifecycle class: declared
     `args_schema`, persistence hooks, executed through `.execute()`
  3. any LangChain `BaseTool` (`@tool`, `StructuredTool`, ...) — passed through

Everything is normalized here to the loop's internal currency (LangChain
`BaseTool` — what `bind_tools` and `ToolNode` consume) exactly once, at the
boundary. Authors never perform or perceive that conversion.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, List, Type, Union

from langchain_core.tools import BaseTool, StructuredTool

from visvoai.core.tools import BaseAgentTool

ToolLike = Union[BaseTool, BaseAgentTool, Type[BaseAgentTool], Callable[..., Any]]


def as_tool(obj: ToolLike) -> BaseTool:
    """Normalize one tool of any supported shape to the loop's currency."""
    if isinstance(obj, BaseTool):
        return obj
    if isinstance(obj, type) and issubclass(obj, BaseAgentTool):
        obj = obj()
    if isinstance(obj, BaseAgentTool):
        return _agent_tool_to_base_tool(obj)
    if callable(obj):
        return _callable_to_base_tool(obj)
    raise TypeError(
        f"Not a tool: {obj!r} — expected a function, a BaseAgentTool "
        "subclass/instance, or a LangChain BaseTool."
    )


def as_tools(objs: Iterable[ToolLike]) -> List[BaseTool]:
    return [as_tool(o) for o in objs]


def as_tools_map(objs: Iterable[ToolLike]) -> Dict[str, BaseTool]:
    tools = as_tools(objs)
    return {t.name: t for t in tools}


def _callable_to_base_tool(fn: Callable[..., Any]) -> BaseTool:
    name = getattr(fn, "__name__", None)
    if not name or name == "<lambda>":
        raise TypeError("Tool functions need a real name (no lambdas).")
    if not (fn.__doc__ or "").strip():
        raise TypeError(
            f"Tool function '{name}' needs a docstring — it becomes the "
            "description the model routes on."
        )
    kwargs: Dict[str, Any] = dict(name=name, description=fn.__doc__.strip())
    if inspect.iscoroutinefunction(fn):
        return StructuredTool.from_function(coroutine=fn, **kwargs)
    return StructuredTool.from_function(func=fn, **kwargs)


def _agent_tool_to_base_tool(tool: BaseAgentTool) -> BaseTool:
    """The adapter both shipping consumers previously built privately:
    schema from the declared `args_schema` (or `llm_schema` when the LLM-facing
    shape differs), execution through `.execute()` so the persistence
    lifecycle (on_start/on_complete/on_error) always runs."""

    def _run(**kwargs: Any) -> Any:
        return tool.execute(**kwargs)

    return StructuredTool.from_function(
        func=_run,
        name=tool.name,
        description=tool.description,
        args_schema=tool.llm_schema or tool.args_schema,
    )
