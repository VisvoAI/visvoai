"""
store.py — file-based conversation persistence (NO database, NO checkpointer).

Layout (folder per conversation; branches are first-class folders):
  <project>/.visvoai/config.toml                      ← in-repo anchor (project_id)
  $VISVOAI_HOME/projects/<pid>/checkpoints.git/       ← shadow repo (see checkpoints.py)
  $VISVOAI_HOME/projects/<pid>/conversations/<cid>/
        meta.json          ← conversation facts: title, active_branch, msg_count, …
        checkpoints.jsonl  ← REGISTRY (shared): {id → commit} — the shadow mapping only
        branches/<name>/
              thread.jsonl     ← this branch's messages (one serialized message/line)
              receipts.jsonl   ← this branch's per-turn UI metadata
              timeline.jsonl   ← this branch's turn/tool→checkpoint view rows
              meta.json        ← branch facts: tip checkpoint id, forked_from, …

Two-level split (cli-git-structure): the conversation owns the immutable code
mapping (`checkpoints.jsonl`: checkpoint id → shadow commit), while each branch
owns its own *view* — thread, receipts, and the ordered timeline that maps its
turns/tool-batches to checkpoint ids. A branch reconstructs itself ONLY from its own
folder; it resolves a checkpoint id against the shared append-only registry but never
reads another branch's mutable state. Fork = deep-copy a branch folder (+ truncate);
the heavy code stays shared as content-addressed, immutable shadow commits.

The durable state of a coding session IS the message thread — serialized
(messages_to_dict) and replayed on resume, never a mid-graph checkpoint.

VISVOAI_HOME overrides the global root (defaults to ~/.visvoai) — used by tests.
All side-effecting calls are lazy: nothing here runs at import or app construction.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict

DEFAULT_BRANCH = "main"


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


def find_project_id(cwd: str) -> str | None:
    """Read-only project_id lookup. Returns None when no `.visvoai/config.toml`
    exists in cwd or any parent (no side effects — doesn't write one). Used by
    the welcome banner to distinguish 'first time in this dir' from 'returning
    user' without forcing a project anchor."""
    import tomllib

    start = Path(cwd).resolve()
    for d in [start, *start.parents]:
        cfg = d / ".visvoai" / "config.toml"
        if cfg.exists():
            try:
                return tomllib.loads(cfg.read_text()).get("project_id")
            except (OSError, tomllib.TOMLDecodeError):
                return None
    return None


def has_conversations(project_id: str) -> bool:
    """True iff at least one conversation folder exists under this project.
    Read-only — does not create the conversations directory. Used by the
    welcome banner to decide between onboarding and history copy."""
    root = visvoai_home() / "projects" / project_id / "conversations"
    if not root.exists():
        return False
    return any(d.is_dir() for d in root.iterdir())


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


def checkpoints_disabled_reason(cwd: str) -> Optional[str]:
    """Why the shadow checkpoint repo must NOT run for this cwd, or None if it's fine.
    Snapshotting the home directory (or the filesystem root, or any ancestor of the
    visvoai data dir) is never intended — `git add -A` would try to stage an enormous
    tree (and would sweep in `~/.visvoai` itself). Returns a short human reason for the
    'checkpointing off' notice; None means checkpointing is safe."""
    try:
        root = project_root(cwd).resolve()
        vh = visvoai_home().resolve()
    except OSError:
        return None
    # vh (~/.visvoai) is under $HOME, so `vh under root` is true exactly when root is
    # the home dir, the filesystem root, or another ancestor of the data dir.
    if vh == root or vh.is_relative_to(root):
        return "the working directory is your home directory (or filesystem root)"
    return None


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:8]


# ── paths ─────────────────────────────────────────────────────────────────────
def _conversations_root(project_id: str) -> Path:
    d = visvoai_home() / "projects" / project_id / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conv_dir(project_id: str, conv_id: str) -> Path:
    """The conversation's own folder — NOT created (reads must not have side effects)."""
    return _conversations_root(project_id) / conv_id


def _ensure_conv_dir(project_id: str, conv_id: str) -> Path:
    d = _conv_dir(project_id, conv_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def conversation_dir(project_id: str, conv_id: str) -> Path:
    """The conversation's folder (created) — a home for auxiliary per-conversation
    files like rendered diagram HTML."""
    return _ensure_conv_dir(project_id, conv_id)


def _meta_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "meta.json"


def _registry_path(project_id: str, conv_id: str) -> Path:
    return _conv_dir(project_id, conv_id) / "checkpoints.jsonl"


def _safe_branch(name: str) -> str:
    """A filesystem-safe branch slug (the on-disk branch folder name)."""
    return "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name) or "branch"


def _branch_dir(project_id: str, conv_id: str, branch: str) -> Path:
    return _conv_dir(project_id, conv_id) / "branches" / _safe_branch(branch)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── conversation meta ───────────────────────────────────────────────────────
def read_meta(project_id: str, conv_id: str) -> dict:
    """Conversation facts (title, active_branch, msg_count, created, updated), or {}."""
    p = _meta_path(project_id, conv_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_meta(project_id: str, conv_id: str, **fields) -> dict:
    """Merge `fields` into the conversation meta and atomically rewrite. `created` is
    stamped once; `updated` on every write. Returns the merged meta."""
    meta = read_meta(project_id, conv_id)
    meta["id"] = conv_id
    meta.setdefault("created", _now_iso())
    meta.setdefault("active_branch", DEFAULT_BRANCH)
    meta.update({k: v for k, v in fields.items() if v is not None})
    meta["updated"] = _now_iso()
    _ensure_conv_dir(project_id, conv_id)
    _atomic_json(_meta_path(project_id, conv_id), meta)
    return meta


def active_branch(project_id: str, conv_id: str) -> str:
    return read_meta(project_id, conv_id).get("active_branch", DEFAULT_BRANCH)


# ── checkpoint registry (shared, append-only, immutable: id → shadow commit) ──
def append_registry(project_id: str, conv_id: str, checkpoint_id: str, commit: str) -> None:
    """Record a checkpoint id → shadow-repo commit mapping. Append-only and immutable:
    an id always maps to the same commit, so any branch may resolve it forever (even
    after the commit is abandoned — a per-checkpoint ref keeps it reachable)."""
    _ensure_conv_dir(project_id, conv_id)
    with _registry_path(project_id, conv_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": checkpoint_id, "commit": commit,
                            "created": _now_iso()}, ensure_ascii=False) + "\n")


def read_registry(project_id: str, conv_id: str) -> List[dict]:
    return _read_jsonl(_registry_path(project_id, conv_id))


def registry_commit(project_id: str, conv_id: str, checkpoint_id: str) -> Optional[str]:
    """Resolve a checkpoint id to its shadow commit (None if unknown)."""
    for rec in read_registry(project_id, conv_id):
        if rec.get("id") == checkpoint_id:
            return rec.get("commit")
    return None


# ── branch meta ──────────────────────────────────────────────────────────────
def read_branch_meta(project_id: str, conv_id: str, branch: str) -> dict:
    p = _branch_dir(project_id, conv_id, branch) / "meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_branch_meta(project_id: str, conv_id: str, branch: str, **fields) -> dict:
    """Branch facts: `tip` (checkpoint id), `forked_from` ({branch, checkpoint_id} or
    None — provenance ONLY, never used to reconstruct history), created, updated."""
    meta = read_branch_meta(project_id, conv_id, branch)
    meta["name"] = branch
    meta.setdefault("created", _now_iso())
    # forked_from may legitimately be set to None; merge it explicitly.
    for k, v in fields.items():
        meta[k] = v
    meta["updated"] = _now_iso()
    d = _branch_dir(project_id, conv_id, branch)
    d.mkdir(parents=True, exist_ok=True)
    _atomic_json(d / "meta.json", meta)
    return meta


def list_branches(project_id: str, conv_id: str) -> List[str]:
    root = _conv_dir(project_id, conv_id) / "branches"
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def ensure_branch(project_id: str, conv_id: str, branch: str) -> None:
    """Create an empty branch folder (thread + meta) if it doesn't exist yet."""
    d = _branch_dir(project_id, conv_id, branch)
    if d.exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "thread.jsonl").touch()
    write_branch_meta(project_id, conv_id, branch, tip=None, forked_from=None)


def copy_branch(project_id: str, conv_id: str, src: str, dst: str) -> None:
    """Deep-copy a branch folder (thread + receipts + timeline + meta) → a NEW branch.
    The fork is fully self-contained: later changes to `src` never touch it."""
    s = _branch_dir(project_id, conv_id, src)
    d = _branch_dir(project_id, conv_id, dst)
    shutil.copytree(s, d)



# thread.jsonl format marker — first line of every NEW thread file. The message
# rows themselves are langchain's serialization (the persistence seam); this
# stamp is the migration door if that format ever has to change. Old files
# without a marker are implicitly v1; the loader skips marker rows either way.
THREAD_FORMAT_MARKER = {"__visvoai_format__": 1}

# ── branch thread ────────────────────────────────────────────────────────────
def _branch_thread_path(project_id: str, conv_id: str, branch: str) -> Path:
    return _branch_dir(project_id, conv_id, branch) / "thread.jsonl"


def append_branch_messages(project_id: str, conv_id: str, branch: str,
                           messages: List[BaseMessage]) -> None:
    """Append new messages to a branch's thread (one serialized message/line).
    Append-only tail write — O(new), never clobbers prior turns."""
    if not messages:
        return
    p = _branch_thread_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8") as f:
        if fresh:
            f.write(json.dumps(THREAD_FORMAT_MARKER) + "\n")
        for d in messages_to_dict(messages):
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def write_branch_thread(project_id: str, conv_id: str, branch: str,
                        messages: List[BaseMessage]) -> None:
    """Overwrite a branch's thread (used to truncate on rewind / seed a fork)."""
    p = _branch_thread_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_lines(p, ([json.dumps(THREAD_FORMAT_MARKER)]
                      + [json.dumps(d, ensure_ascii=False) for d in messages_to_dict(messages)]))


def load_branch_thread(project_id: str, conv_id: str, branch: str) -> List[BaseMessage]:
    p = _branch_thread_path(project_id, conv_id, branch)
    if not p.exists():
        return []
    try:
        rows = [r for r in _read_jsonl(p) if "__visvoai_format__" not in r]
        return messages_from_dict(rows)
    except (json.JSONDecodeError, OSError):
        return []


# ── branch receipts ──────────────────────────────────────────────────────────
def _branch_receipts_path(project_id: str, conv_id: str, branch: str) -> Path:
    return _branch_dir(project_id, conv_id, branch) / "receipts.jsonl"


def append_branch_receipt(project_id: str, conv_id: str, branch: str, receipt: dict) -> None:
    p = _branch_receipts_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def read_branch_receipts(project_id: str, conv_id: str, branch: str) -> List[dict]:
    return _read_jsonl(_branch_receipts_path(project_id, conv_id, branch))


def truncate_branch_receipts(project_id: str, conv_id: str, branch: str, n: int) -> None:
    """Keep only the first `n` receipts (rewind drops receipts for turns that no longer
    exist on this branch)."""
    p = _branch_receipts_path(project_id, conv_id, branch)
    kept = read_branch_receipts(project_id, conv_id, branch)[:max(0, n)]
    if not kept:
        if p.exists():
            p.unlink()
        return
    _atomic_lines(p, (json.dumps(r, ensure_ascii=False) for r in kept))


def keep_last_branch_receipts(project_id: str, conv_id: str, branch: str, n: int) -> None:
    """Keep only the LAST `n` receipts (compaction folds older turns → their receipts go
    too, so replay pairs the kept turns with the right footers)."""
    p = _branch_receipts_path(project_id, conv_id, branch)
    kept = read_branch_receipts(project_id, conv_id, branch)[-n:] if n > 0 else []
    if not kept:
        if p.exists():
            p.unlink()
        return
    _atomic_lines(p, (json.dumps(r, ensure_ascii=False) for r in kept))


# ── branch timeline (turn/tool-batch → checkpoint view) ───────────────────────
def _branch_timeline_path(project_id: str, conv_id: str, branch: str) -> Path:
    return _branch_dir(project_id, conv_id, branch) / "timeline.jsonl"


def append_timeline(project_id: str, conv_id: str, branch: str, row: dict) -> None:
    """Append one ordered view row: {checkpoint_id, message_index, kind, label}."""
    p = _branch_timeline_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_timeline(project_id: str, conv_id: str, branch: str) -> List[dict]:
    """A branch's ordered timeline rows (oldest→newest). This IS the branch's
    turn/tool→checkpoint mapping — no DAG walk needed."""
    return _read_jsonl(_branch_timeline_path(project_id, conv_id, branch))


def write_timeline(project_id: str, conv_id: str, branch: str, rows: List[dict]) -> None:
    """Overwrite a branch's timeline (used to truncate on rewind)."""
    p = _branch_timeline_path(project_id, conv_id, branch)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        if p.exists():
            p.unlink()
        return
    _atomic_lines(p, (json.dumps(r, ensure_ascii=False) for r in rows))


# ── seeding / export helpers ─────────────────────────────────────────────────
def seed_conversation(project_id: str, conv_id: str, messages: List[BaseMessage],
                      receipts: List[dict], *, title: Optional[str] = None,
                      model: Optional[str] = None) -> None:
    """Create a fresh conversation with a single `main` branch (used by /fork to seed
    the forked working directory's store). No checkpoints/timeline — the fork's first
    turn lays its own baseline."""
    ensure_branch(project_id, conv_id, DEFAULT_BRANCH)
    write_branch_thread(project_id, conv_id, DEFAULT_BRANCH, messages)
    if receipts:
        _atomic_lines(_branch_receipts_path(project_id, conv_id, DEFAULT_BRANCH),
                      (json.dumps(r, ensure_ascii=False) for r in receipts))
    write_meta(project_id, conv_id, active_branch=DEFAULT_BRANCH,
               title=title or title_for(messages), model=model, msg_count=len(messages))


def write_thread_to(path: Path, messages: List[BaseMessage]) -> None:
    """Serialize a thread to an arbitrary path — used by export (outside the store)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_lines(path, (json.dumps(d, ensure_ascii=False) for d in messages_to_dict(messages)))


# ── list / load (active-branch aware) ─────────────────────────────────────────
def list_conversations(project_id: str) -> List[dict]:
    """Newest-first {id, title, when, msgs} rows for the SessionsScreen. Prefers the
    conversation meta (title/active_branch/msg_count/updated); falls back to the active
    branch's thread when meta is incomplete."""
    root = _conversations_root(project_id)
    out: List[dict] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        out.append(_summary(project_id, d.name))
    out.sort(key=lambda s: s["_sort"], reverse=True)
    return out


def load_conversation(project_id: str, conv_id: str) -> List[BaseMessage]:
    """The active branch's thread. Raises if the conversation doesn't exist."""
    if not _conv_dir(project_id, conv_id).exists():
        raise FileNotFoundError(f"conversation {conv_id} not found")
    return load_branch_thread(project_id, conv_id, active_branch(project_id, conv_id))


# ── conversation-level convenience (operate on the active/default branch) ─────
# Most callers think in "the conversation's thread/receipts"; branches are an
# implementation detail. These delegate to the active branch (default 'main').
def save_conversation(project_id: str, conv_id: str, messages: List[BaseMessage],
                      title: Optional[str] = None) -> None:
    """(Over)write the active branch's thread (seeds 'main' for a new conversation)."""
    b = active_branch(project_id, conv_id)
    ensure_branch(project_id, conv_id, b)
    write_branch_thread(project_id, conv_id, b, messages)


def append_messages(project_id: str, conv_id: str, messages: List[BaseMessage]) -> None:
    """Append to the active branch's thread."""
    b = active_branch(project_id, conv_id)
    ensure_branch(project_id, conv_id, b)
    append_branch_messages(project_id, conv_id, b, messages)


def append_receipt(project_id: str, conv_id: str, receipt: dict) -> None:
    """Append a per-turn receipt to the active branch."""
    append_branch_receipt(project_id, conv_id, active_branch(project_id, conv_id), receipt)


def read_receipts(project_id: str, conv_id: str) -> List[dict]:
    """The active branch's per-turn receipts."""
    return read_branch_receipts(project_id, conv_id, active_branch(project_id, conv_id))


def _summary(project_id: str, conv_id: str) -> dict:
    meta = read_meta(project_id, conv_id)
    branch = meta.get("active_branch", DEFAULT_BRANCH)
    thread_file = _branch_thread_path(project_id, conv_id, branch)
    title = meta.get("title")
    msgs = meta.get("msg_count")
    if title is None or msgs is None:
        try:
            dicts = [r for r in _read_jsonl(thread_file)
                     if "__visvoai_format__" not in r]
        except (json.JSONDecodeError, OSError):
            dicts = []
        title = title or _title_from_dicts(dicts)
        msgs = msgs if msgs is not None else len(dicts)
    mtime_ns = (thread_file.stat().st_mtime_ns if thread_file.exists()
                else _conv_dir(project_id, conv_id).stat().st_mtime_ns)
    when_dt = _parse_iso(meta.get("updated")) or datetime.fromtimestamp(mtime_ns / 1e9, timezone.utc)
    return {"id": conv_id, "title": title, "when": _relative(when_dt),
            "msgs": msgs, "_sort": when_dt.timestamp()}


# ── shared low-level ──────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def _atomic_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _atomic_lines(path: Path, lines) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    tmp.replace(path)


def title_for(messages: List[BaseMessage]) -> str:
    """Conversation title from live messages (first human turn)."""
    return _title_from_dicts(messages_to_dict(messages))


def _title_from_dicts(dicts: List[dict]) -> str:
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


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


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
