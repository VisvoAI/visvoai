"""Tests for per-round tool retrieval wiring in build_graph + make_per_round_retrieve.

Pins the contract that makes semantic tool retrieval functional in the open
package:

  - make_per_round_retrieve(catalog) ranks tools BM25-only when embed_query=None
    (zero embedding infrastructure)
  - with a retriever set, each round binds only core_tools + the retrieved subset
  - with no retriever, every tool is bound (bind-everything, backward compatible)
  - _intent_query uses the most recent human message
"""
import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from visvoai.core import ToolCatalog, make_per_round_retrieve
from visvoai.core.graph import _intent_query, build_graph


@tool
def core_tool(x: str) -> str:
    """a core tool"""
    return x


@tool
def weather__get_forecast(x: str) -> str:
    """get weather forecast for a city"""
    return x


@tool
def db__run_query(x: str) -> str:
    """run a SQL query against the database"""
    return x


class _FakeBound:
    def __init__(self, names, sink):
        self._names = names
        self._sink = sink

    async def ainvoke(self, _messages):
        self._sink.append(self._names)
        return AIMessage(content="done")


class _FakeModel:
    """Duck-typed chat model: records the tool set bound on each ainvoke."""

    def __init__(self):
        self.bound_sets = []

    def bind_tools(self, tools):
        return _FakeBound(sorted(t.name for t in tools), self.bound_sets)


def _catalog():
    return ToolCatalog([
        ("weather__get_forecast", "get weather forecast for a city", None),
        ("db__run_query", "run a SQL query against the database", None),
    ])


def test_make_per_round_retrieve_bm25_without_embeddings():
    retrieve = make_per_round_retrieve(_catalog(), k=1, embed_query=None)
    assert retrieve("what is the weather forecast tomorrow") == ["weather__get_forecast"]


def test_intent_query_uses_last_human_message():
    msgs = [HumanMessage(content="first"), AIMessage(content="hi"), HumanMessage(content="LAST")]
    assert _intent_query(msgs) == "LAST"


def test_retrieval_binds_core_plus_retrieved():
    model = _FakeModel()
    all_map = {t.name: t for t in (core_tool, weather__get_forecast, db__run_query)}
    graph = build_graph(
        model, [core_tool], all_map, "sys",
        per_round_retrieve=make_per_round_retrieve(_catalog(), k=1),
    )
    asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="weather forecast please")]}))
    assert model.bound_sets[-1] == ["core_tool", "weather__get_forecast"]


def test_no_retriever_binds_everything():
    model = _FakeModel()
    all_map = {t.name: t for t in (core_tool, weather__get_forecast, db__run_query)}
    graph = build_graph(model, [core_tool], all_map, "sys", per_round_retrieve=None)
    asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="hi")]}))
    assert model.bound_sets[-1] == ["core_tool", "db__run_query", "weather__get_forecast"]
