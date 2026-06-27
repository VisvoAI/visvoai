"""
store.py — file-based conversation persistence (NO database, NO checkpointer).

Layout (a folder per conversation, so auxiliary files have a clean home):
  <project>/.visvoai/config.toml                      ← in-repo anchor (project_id)
  $VISVOAI_HOME/projects/<pid>/conversations/<cid>/   ← one dir per conversation
        history.jsonl   ← append-only message log (one serialized message/line)
        meta.json       ← mutable facts (title, created, updated, model, msg_count)
        (future: cache/ for large-output overflow, attachments, …)

The durable state of a coding session IS the message thread, so we serialize it
(messages_to_dict) and replay on resume — never a mid-graph checkpoint. Each
conversation's history is APPEND-ONLY: a turn appends only its new messages, so a
save is O(new) and can never clobber prior history.

VISVOAI_HOME overrides the global root (defaults to ~/.visvoai) — used by tests.
All side-effecting calls are lazy: nothing here runs at import or app construction.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict


def visvoai_home() -> Path:
    return Path(os.environ.get("VISVOAI_HOME") or (Path.home() / ".visvoai"))


def resolve_project_id(cwd: str) -> str:
    """Find the project's id by walking up for a .visvoai/config.toml (like git
    finds .git); if none, create one in cwd. Stable across moves/renames."""
    import tomllib

    start = Path(cwd).resolve()
    for d in [start, *start.parents]:
        cfg = d / ".visvoai" / "config.toml"
        if cfg.exists():
            pid = tomllib.loads(cfg.read_text()).get("project_id")
            if pid:
                return pid
            return _write_project_id(cfg)
    return _write_project_id(start / ".visvoai" / "config.toml")


def _write_project_id(cfg: Path) -> str:
    cfg.parent.mkdir(parents=True, exist_ok=True)
    pid = uuid.uuid4().hex[:12]
    cfg.write_text(f'project_id = "{pid}"\n')
    return pid


def project_root(cwd: str) -> Path:
    """The project's root — the dir holding `.visvoai/config.toml` (walk up, like git
    finds `.git`), or `cwd` itself if none exists yet. The shadow checkpoint repo uses
    this as its work tree so snapshots are stable no matter which subdir the CLI was
    launched from. Pair with `resolve_project_id` (which creates the anchor) first."""
    start = Path(cwd).resolve()
    for d in [start, *start.parents]:
        if (d / ".visvoai" / "config.toml").exists():
            return d
    return start


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:8]


def _conversations_root(project_id: str) -> Path:
    d = visvoai_home() / "projects" / project_id / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conv_dir(project_id: str, conv_id: str) -> Path:
    """The conversation's own folder — NOT created (reads must not have side effects).
    Writers call _ensure_conv_dir first."""
    return _conversations_root(project_id) / conv_id


def _ensure_conv_dir(project_id: str, conv_id: str) -> Path:
    d = _conv_dir(project_id, conv_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def conversation_dir(project_id: str, conv_id: str) -> Path:
    """The conversation's folder (created) — a home for auxiliary per-conversation
    files like rendered diagram HTML, distinct from the history/meta writers."""
    return _ensure_conv_dir(project_id, conv_id)


def _conv_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "history.jsonl"


def _meta_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "meta.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _receipts_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "receipts.jsonl"


def append_receipt(project_id: str, conv_id: str, receipt: dict) -> None:
    """Append a per-turn UI receipt (duration, model, thinking, tokens, cost). This
    is UI metadata ONLY — NOT message history, so it never enters the model context;
    it's replayed on resume + summed for the conversation cost."""
    _ensure_conv_dir(project_id, conv_id)
    with _receipts_path(project_id, conv_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def write_receipts(project_id: str, conv_id: str, receipts: List[dict]) -> None:
    """Overwrite the active receipts log with exactly `receipts` (used on branch
    switch, where the active branch's receipts are swapped wholesale). Atomic."""
    p = _receipts_path(project_id, conv_id)
    _ensure_conv_dir(project_id, conv_id)
    if not receipts:
        if p.exists():
            p.unlink()
        return
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in receipts:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


def save_branch_receipts(project_id: str, conv_id: str, branch: str,
                         receipts: List[dict]) -> None:
    """Persist a branch's receipts alongside its thread (UI metadata; mirrors
    save_branch_thread so footers/cost are correct per branch)."""
    p = _branch_thread_path(project_id, conv_id, branch).with_suffix(".receipts.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in receipts:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


def load_branch_receipts(project_id: str, conv_id: str, branch: str) -> List[dict]:
    p = _branch_thread_path(project_id, conv_id, branch).with_suffix(".receipts.jsonl")
    if not p.exists():
        return []
    try:
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def truncate_receipts(project_id: str, conv_id: str, n: int) -> None:
    """Keep only the first `n` per-turn receipts (rewind drops the receipts for turns
    that no longer exist). Atomic rewrite; removes the file when n <= 0."""
    p = _receipts_path(project_id, conv_id)
    if not p.exists():
        return
    kept = read_receipts(project_id, conv_id)[:max(0, n)]
    if not kept:
        p.unlink()
        return
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


def read_receipts(project_id: str, conv_id: str) -> List[dict]:
    """Per-turn receipts in order (empty if none)."""
    p = _receipts_path(project_id, conv_id)
    if not p.exists():
        return []
    try:
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def _checkpoints_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "checkpoints.jsonl"


def append_checkpoint(project_id: str, conv_id: str, checkpoint: dict) -> None:
    """Append one checkpoint record to the conversation's append-only checkpoint log.
    A checkpoint is `{id, message_index, parent, commit, kind, branch, label,
    created}` — the conversation↔code mapping (`commit` is the shadow-repo commit sha;
    the code DAG itself lives in the shadow git repo). NEVER rewritten: rewinds/branches append new records, the active view is
    derived by walking `parent` links from the active branch tip."""
    _ensure_conv_dir(project_id, conv_id)
    with _checkpoints_path(project_id, conv_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")


def read_checkpoints(project_id: str, conv_id: str) -> List[dict]:
    """All checkpoint records in append order (empty if none)."""
    p = _checkpoints_path(project_id, conv_id)
    if not p.exists():
        return []
    try:
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def read_meta(project_id: str, conv_id: str) -> dict:
    """The conversation's metadata sidecar (title, created, updated, model, …), or
    {} if none yet. The JSONL log holds history; this holds the mutable facts."""
    p = _meta_path(project_id, conv_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_meta(project_id: str, conv_id: str, **fields) -> dict:
    """Merge `fields` into the conversation's metadata sidecar and atomically rewrite.
    `created` is stamped once; `updated` on every write. Returns the merged meta."""
    meta = read_meta(project_id, conv_id)
    meta["id"] = conv_id
    meta.setdefault("created", _now_iso())
    meta.update({k: v for k, v in fields.items() if v is not None})
    meta["updated"] = _now_iso()
    _ensure_conv_dir(project_id, conv_id)
    p = _meta_path(project_id, conv_id)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    tmp.replace(p)
    return meta


def append_messages(project_id: str, conv_id: str, messages: List[BaseMessage]) -> None:
    """Append new messages to the conversation's JSONL log (one serialized message
    per line). Append-only: prior turns are never rewritten, so a save can never
    clobber existing history, and the cost is O(new messages), not O(thread)."""
    if not messages:
        return
    _ensure_conv_dir(project_id, conv_id)
    path = _conv_path(project_id, conv_id)
    with path.open("a", encoding="utf-8") as f:
        for d in messages_to_dict(messages):
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def _safe_branch(name: str) -> str:
    """A filesystem-safe branch slug (the on-disk thread file name)."""
    return "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name) or "branch"


def _branch_thread_path(project_id: str, conv_id: str, branch: str) -> Path:
    return _conv_dir(project_id, conv_id) / "branches" / f"{_safe_branch(branch)}.jsonl"


def save_branch_thread(project_id: str, conv_id: str, branch: str,
                       messages: List[BaseMessage]) -> None:
    """Persist a branch's full thread (its own linearization). The ACTIVE branch also
    mirrors to history.jsonl so resume/list keep working unchanged; non-active branches
    live only here until switched to."""
    p = _branch_thread_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for d in messages_to_dict(messages):
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    tmp.replace(p)


def load_branch_thread(project_id: str, conv_id: str, branch: str) -> List[BaseMessage]:
    """A branch's saved thread (empty list if none recorded yet)."""
    p = _branch_thread_path(project_id, conv_id, branch)
    if not p.exists():
        return []
    try:
        return messages_from_dict(_read_lines(p))
    except (json.JSONDecodeError, OSError):
        return []


def save_conversation(project_id: str, conv_id: str, messages: List[BaseMessage],
                      title: Optional[str] = None) -> None:
    """(Over)write the whole conversation as JSONL, atomically — used to seed or
    rewrite a thread. The live turn path uses append_messages. `title` is accepted
    for API compatibility but ignored (titles are derived from the first turn)."""
    _ensure_conv_dir(project_id, conv_id)
    path = _conv_path(project_id, conv_id)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for d in messages_to_dict(messages):
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _read_lines(path: Path) -> List[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def list_conversations(project_id: str) -> List[dict]:
    """Newest-first list of {id, title, when, msgs} for the SessionsScreen. Scans the
    per-conversation folders. Prefers the meta sidecar (title/updated); falls back to
    parsing history only when meta is missing."""
    root = _conversations_root(project_id)
    out: List[dict] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        hist = d / "history.jsonl"
        mtime = hist.stat().st_mtime_ns if hist.exists() else d.stat().st_mtime_ns
        out.append(_summary(project_id, d.name, hist, mtime))
    out.sort(key=lambda s: s["_sort"], reverse=True)
    return out


def load_conversation(project_id: str, conv_id: str) -> List[BaseMessage]:
    hist = _conv_path(project_id, conv_id)
    if hist.exists():
        return messages_from_dict(_read_lines(hist))
    raise FileNotFoundError(f"conversation {conv_id} not found")


def _summary(project_id: str, conv_id: str, hist_file: Path, mtime_ns: int) -> dict:
    """One SessionsScreen row. Title/updated/msgs come from the meta sidecar when
    present; otherwise they're derived from the history file (pre-meta)."""
    meta = read_meta(project_id, conv_id)
    title = meta.get("title")
    msgs = meta.get("msg_count")
    updated = meta.get("updated")
    if title is None or msgs is None:   # no/partial meta → fall back to the history
        try:
            dicts = _read_lines(hist_file) if hist_file.exists() else []
        except (json.JSONDecodeError, OSError):
            dicts = []
        title = title or _title_from_dicts(dicts)
        msgs = msgs if msgs is not None else len(dicts)
    when_dt = _parse_iso(updated) or datetime.fromtimestamp(mtime_ns / 1e9, timezone.utc)
    return {
        "id": conv_id,
        "title": title,
        "when": _relative(when_dt),
        "msgs": msgs,
        "_sort": when_dt.timestamp(),
    }


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def title_for(messages: List[BaseMessage]) -> str:
    """Conversation title from live messages (first human turn) — used for the
    terminal tab. Same rule as the on-disk title derivation."""
    return _title_from_dicts(messages_to_dict(messages))


def _title_from_dicts(dicts: List[dict]) -> str:
    """Title = the first human turn, flattened (handles str or list-of-blocks content)."""
    for d in dicts:
        if d.get("type") == "human":
            c = d.get("data", {}).get("content")
            text = c if isinstance(c, str) else _flatten_blocks(c)
            text = " ".join(text.split())
            return (text[:50] + "…") if len(text) > 50 else (text or "(untitled)")
    return "(untitled)"


def _flatten_blocks(content) -> str:
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


def _relative(then: datetime) -> str:
    delta = datetime.now(timezone.utc) - then
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"
