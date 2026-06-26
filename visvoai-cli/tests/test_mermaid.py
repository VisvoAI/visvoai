"""Mermaid diagrams → an HTML viewer opened in the browser.

The terminal can't draw mermaid, so a ```mermaid fence gets a 'view diagram' link
under the answer; clicking it writes a self-contained HTML file into the
conversation folder and opens it. Pure helpers tested directly; the link + click
flow tested through a fake-graph turn.
"""
import pytest

from visvoai.cli import VisvoApp, agent, mermaid
from visvoai.cli.widgets import Assistant, MermaidCard

_DIAGRAM = "graph TD\n  A[Start] --> B{Choice}\n  B --> C[End]"
_ANSWER = f"Here is the flow:\n\n```mermaid\n{_DIAGRAM}\n```\n\nThat's it."


# ── pure helpers ────────────────────────────────────────────────────────────
def test_extract_mermaid_finds_fenced_blocks():
    assert mermaid.extract_mermaid(_ANSWER) == [_DIAGRAM]


def test_extract_mermaid_ignores_other_fences_and_empty():
    assert mermaid.extract_mermaid("```python\nx = 1\n```") == []
    assert mermaid.extract_mermaid("```mermaid\n\n```") == []
    assert mermaid.extract_mermaid("") == []


def test_extract_mermaid_multiple_in_order():
    text = "```mermaid\nA\n```\nmid\n```mermaid\nB\n```"
    assert mermaid.extract_mermaid(text) == ["A", "B"]


def test_split_segments_interleaves_text_and_mermaid():
    segs = mermaid.split_segments(_ANSWER)
    kinds = [k for k, _ in segs]
    assert kinds == ["text", "mermaid", "text"]
    assert segs[1] == ("mermaid", _DIAGRAM)
    assert segs[0][1].strip() == "Here is the flow:"
    assert segs[2][1].strip() == "That's it."


def test_split_segments_plain_text_is_single_segment():
    assert mermaid.split_segments("just words") == [("text", "just words")]


def test_extract_mermaid_tolerates_case_variants():
    # The model may emit ```Mermaid — case must not defeat detection. But a bare
    # ``` fence is NEVER treated as a diagram (would mis-render ordinary code).
    assert mermaid.extract_mermaid("```Mermaid\ngraph TD\n  A-->B\n```") == ["graph TD\n  A-->B"]
    assert mermaid.extract_mermaid("```\ngraph TD\n  A-->B\n```") == []


def test_write_diagram_html_is_content_hashed_and_idempotent(tmp_path):
    p1 = mermaid.write_diagram_html(tmp_path, _DIAGRAM)
    p2 = mermaid.write_diagram_html(tmp_path, _DIAGRAM)
    assert p1 == p2 and p1.exists()
    assert p1.name.startswith("diagram-") and p1.suffix == ".html"
    other = mermaid.write_diagram_html(tmp_path, "graph LR\n  X --> Y")
    assert other != p1  # distinct source → distinct file


def test_write_diagram_html_escapes_source(tmp_path):
    path = mermaid.write_diagram_html(tmp_path, 'graph TD\n  A["<b> & </b>"]')
    body = path.read_text()
    assert "&lt;b&gt;" in body and "&amp;" in body  # raw < & never reach the markup


# ── link mounts + click flow ────────────────────────────────────────────────
class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeGraph:
    """Streams one answer chunk carrying a mermaid fence, then the final state."""
    async def astream_events(self, state, version="v2", config=None):
        yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(_ANSWER)}}
        from langchain_core.messages import AIMessage, HumanMessage
        yield {"event": "on_chain_end",
               "data": {"output": {"messages": [HumanMessage(content="hi"),
                                                 AIMessage(content=_ANSWER)]}}}


@pytest.mark.asyncio
async def test_mermaid_reflows_to_card_and_click_writes_html(monkeypatch, tmp_path):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agent, "api_key_available", lambda model_id: True)
    monkeypatch.setattr(agent, "build_agent_graph", lambda *a, **k: _FakeGraph())
    opened = []
    monkeypatch.setattr(mermaid, "open_path", lambda path: opened.append(path) or True)

    app = VisvoApp()
    app._cwd = str(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app._run_real_turn("hi")
        await pilot.pause()

        cards = app.query(MermaidCard)
        assert cards, "the ```mermaid fence should reflow into a diagram card"
        assert cards.first().source == _DIAGRAM
        # The raw fence must NOT survive as copyable code in any answer block; the
        # surrounding prose still renders.
        raws = [a._raw for a in app.query(Assistant)]
        assert all("mermaid" not in r for r in raws), "raw fence should be stripped"
        assert any("Here is the flow" in r for r in raws)

        app.on_mermaid_card_clicked(MermaidCard.Clicked(_DIAGRAM))
        await pilot.pause()

        assert opened, "clicking the card should open the rendered HTML"
        assert opened[0].exists() and opened[0].suffix == ".html"
