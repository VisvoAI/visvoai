"""Phase 5 — file-based conversation store (project_id + save/list/load).

Uses tmp dirs (VISVOAI_HOME + a tmp project) so it never touches the real home.
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from visvoai.cli import VisvoApp, store


def test_project_id_created_and_stable(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    pid1 = store.resolve_project_id(str(proj))
    assert (proj / ".visvoai" / "config.toml").exists()
    # second resolve reads the same id (stable across calls / moves)
    assert store.resolve_project_id(str(proj)) == pid1


def test_project_id_found_by_walking_up(tmp_path):
    proj = tmp_path / "proj"
    sub = proj / "a" / "b"
    sub.mkdir(parents=True)
    pid = store.resolve_project_id(str(proj))
    # resolving from a nested dir finds the parent's .visvoai
    assert store.resolve_project_id(str(sub)) == pid


def test_save_list_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid = "testproj"
    msgs = [HumanMessage(content="add a rate limiter"), AIMessage(content="done")]
    cid = store.new_conversation_id()
    store.save_conversation(pid, cid, msgs)

    convs = store.list_conversations(pid)
    assert len(convs) == 1
    assert convs[0]["id"] == cid
    assert convs[0]["title"] == "add a rate limiter"   # derived from first human msg
    assert convs[0]["msgs"] == 2

    loaded = store.load_conversation(pid, cid)
    assert [m.content for m in loaded] == ["add a rate limiter", "done"]


def test_list_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid = "p"
    store.save_conversation(pid, "older", [HumanMessage(content="first")])
    store.save_conversation(pid, "newer", [HumanMessage(content="second")])
    ids = [c["id"] for c in store.list_conversations(pid)]
    assert ids[0] == "newer"   # most-recently-updated first


def test_title_for_uses_first_human_turn():
    msgs = [AIMessage(content="hmm"),
            HumanMessage(content="Refactor the auth module please"),
            AIMessage(content="ok")]
    assert store.title_for(msgs) == "Refactor the auth module please"
    # list-of-blocks human content is flattened too
    blocks = [HumanMessage(content=[{"type": "text", "text": "Fix the bug"}])]
    assert store.title_for(blocks) == "Fix the bug"
    assert store.title_for([AIMessage(content="x")]) == "(untitled)"


def test_append_accumulates_across_turns(tmp_path, monkeypatch):
    """Appending each turn's new messages grows one conversation (no clobber)."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid, cid = "p", "c1"
    store.append_messages(pid, cid, [HumanMessage(content="q1"), AIMessage(content="a1")])
    store.append_messages(pid, cid, [HumanMessage(content="q2"), AIMessage(content="a2")])
    loaded = store.load_conversation(pid, cid)
    assert [m.content for m in loaded] == ["q1", "a1", "q2", "a2"]
    convs = store.list_conversations(pid)
    assert convs[0]["msgs"] == 4
    assert convs[0]["title"] == "q1"          # first human turn


def test_meta_sidecar_merge_and_stamps(tmp_path, monkeypatch):
    """write_meta merges fields, stamps created once, bumps updated each write."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid, cid = "p", "c1"
    m1 = store.write_meta(pid, cid, title="First", model="gemini:x", msg_count=2)
    assert m1["title"] == "First" and m1["model"] == "gemini:x"
    created = m1["created"]
    m2 = store.write_meta(pid, cid, title="Refined")     # title updated, created preserved
    assert m2["title"] == "Refined" and m2["created"] == created
    assert m2["model"] == "gemini:x"                     # untouched field survives merge
    assert store.read_meta(pid, cid)["title"] == "Refined"


def test_list_prefers_meta_title(tmp_path, monkeypatch):
    """A meta title (e.g. the LLM-refined one) wins over the derived first-prompt."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid, cid = "p", "c1"
    store.append_messages(pid, cid, [HumanMessage(content="raw first prompt"),
                                     AIMessage(content="a")])
    store.write_meta(pid, cid, title="Nice Refined Title", msg_count=2)
    convs = store.list_conversations(pid)
    assert convs[0]["title"] == "Nice Refined Title"
    assert convs[0]["msgs"] == 2


def test_conversation_is_a_folder(tmp_path, monkeypatch):
    """Each conversation is its own folder: meta.json + a main branch thread."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid, cid = "p", "c1"
    store.append_messages(pid, cid, [HumanMessage(content="hi"), AIMessage(content="yo")])
    store.write_meta(pid, cid, title="Hi", msg_count=2)
    d = store._conv_dir(pid, cid)
    assert d.is_dir()
    assert (d / "branches" / "main" / "thread.jsonl").exists()
    assert (d / "meta.json").exists()


def test_receipts_append_and_read(tmp_path, monkeypatch):
    """Per-turn receipts (UI metadata) round-trip via the sidecar."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    pid, cid = "p", "c1"
    assert store.read_receipts(pid, cid) == []
    store.append_receipt(pid, cid, {"seconds": 4.2, "cost": 0.001, "input_tokens": 1200})
    store.append_receipt(pid, cid, {"seconds": 1.1, "cost": 0.002, "input_tokens": 1800})
    rs = store.read_receipts(pid, cid)
    assert [r["cost"] for r in rs] == [0.001, 0.002]
    assert sum(r["cost"] for r in rs) == 0.003
    # receipts live in the active branch folder
    assert (store._conv_dir(pid, cid) / "branches" / "main" / "receipts.jsonl").exists()


@pytest.mark.asyncio
async def test_persist_skips_human_less_thread(tmp_path, monkeypatch):
    """A degenerate thread (no user turn — what produced the old '(untitled)'
    empty save) is never persisted."""
    monkeypatch.setenv("VISVOAI_HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    app = VisvoApp()
    app._cwd = str(proj)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._history = [AIMessage(content=[])]   # no HumanMessage
        app._persist_turn()
        pid = store.resolve_project_id(str(proj))
        assert store.list_conversations(pid) == []   # nothing saved
        # a proper thread still saves
        app._history = [HumanMessage(content="hello"), AIMessage(content="hi")]
        app._conv_id = None
        app._persist_turn()
        assert len(store.list_conversations(pid)) == 1
