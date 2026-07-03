"""shellsafe — classify shell commands as read vs write, and enforce read at the OS level.

Two independent layers with different jobs:

1. classify_command() — a conservative TEXT classifier. Decides only whether the
   user must be prompted (write) or not (read). It can be fooled; that's fine,
   because anything it calls "read" runs inside the OS sandbox.

2. sandbox_argv() — wraps a command so the KERNEL denies file writes (macOS
   sandbox-exec, Linux bubblewrap). A disguised write that slips past the
   classifier doesn't become a silent mutation — it becomes EPERM.

Failure geometry: misclassifying a write as read ⇒ no prompt, but the sandbox
blocks it (loud error, no mutation). Misclassifying a read as write ⇒ one
unnecessary prompt. Both failure modes are safe; only the first needs the kernel.
"""
from __future__ import annotations

import platform
import shlex
import shutil

# Verbs that only observe. Anything not listed classifies as write — the list is
# deliberately incomplete rather than deliberately complete.
READ_VERBS = frozenset({
    "ls", "cat", "head", "tail", "less", "more", "wc", "file", "stat", "du", "df",
    "grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "tree", "locate",
    "pwd", "echo", "printf", "which", "whereis", "type", "basename", "dirname",
    "readlink", "realpath", "env", "printenv", "date", "whoami", "hostname",
    "uname", "id", "uptime", "ps", "top", "lsof", "arch", "sw_vers", "sysctl",
    "sort", "uniq", "cut", "tr", "diff", "cmp", "comm", "column", "nl", "strings",
    "md5", "md5sum", "shasum", "sha256sum", "cksum", "hexdump", "xxd", "od",
    "jq", "yq", "awk", "sed", "xargs", "tee", "true", "false", "test", "sleep",
})
# read-verbs that flip to write when given specific flags
_WRITE_FLAGS = {
    "sed": ("-i",),          # in-place edit
    "tee": ("*",),           # tee always writes files (unless argv is empty — rare)
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir"),
    "xargs": ("*",),         # xargs runs an arbitrary child verb — classify that instead
}
# git/docker/etc.: read-only only for specific subcommands
_SUBCOMMAND_READ = {
    "git": frozenset({"status", "log", "diff", "show", "branch", "blame", "grep",
                      "ls-files", "ls-tree", "ls-remote", "rev-parse", "describe",
                      "shortlog", "reflog", "remote", "tag", "config", "var",
                      "cat-file", "count-objects", "worktree"}),
    "docker": frozenset({"ps", "images", "logs", "inspect", "version", "info",
                         "stats", "top", "port", "diff", "history"}),
    "docker-compose": frozenset({"ps", "logs", "config", "version", "top", "images"}),
}
# git subcommands above that still mutate with certain flags
_GIT_WRITE_FLAGS = {
    "branch": ("-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy",
               "--set-upstream-to", "--unset-upstream", "--edit-description"),
    "remote": ("add", "remove", "rm", "rename", "set-url", "set-head",
               "set-branches", "prune"),
    "tag": ("-d", "-a", "-s", "-f", "--delete", "-m"),
    "config": ("--unset", "--unset-all", "--replace-all", "--add", "--edit",
               "--rename-section", "--remove-section", "-e"),
    "worktree": ("add", "remove", "prune", "move", "repair", "unlock", "lock"),
    "reflog": ("expire", "delete", "drop"),
    "stash": ("push", "pop", "drop", "apply", "clear", "save", "create", "store"),
}

# Tokens that end one command segment and start another.
_SEPARATORS = {"|", "||", "&&", ";", "&", "\n"}


def _tokenize(command: str) -> list[str] | None:
    """shlex-split with shell punctuation kept as tokens. None → unparseable."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def _split_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _redirect_is_safe(tok: str, nxt: str | None) -> bool | None:
    """True → safe redirect, False → write redirect, None → not a redirect."""
    core = tok.lstrip("0123456789&")
    if not core.startswith((">", "<")):
        return None
    if core.startswith("<"):
        return True                       # input redirect reads
    target = core.lstrip(">&|") or (nxt or "")
    # >&2 / 2>&1: fd duplication, no file touched
    if target in {"1", "2"} and "&" in core:
        return True
    return target == "/dev/null"


def _segment_is_read(seg: list[str]) -> bool:
    # skip leading VAR=val assignments and benign wrappers
    i = 0
    while i < len(seg) and ("=" in seg[i] and not seg[i].startswith("=")):
        i += 1
    while i < len(seg) and seg[i] in {"command", "builtin", "nice", "time", "timeout"}:
        i += 1
        # `timeout 30 cmd` — skip its duration argument
        if seg[i - 1] == "timeout" and i < len(seg) and seg[i][:1].isdigit():
            i += 1
    if i >= len(seg):
        return False
    verb = seg[i].rsplit("/", 1)[-1]      # /usr/bin/grep → grep
    args = seg[i + 1:]

    if verb in _SUBCOMMAND_READ:
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub not in _SUBCOMMAND_READ[verb]:
            return False
        for flag in _GIT_WRITE_FLAGS.get(sub, ()):
            if flag in args:
                return False
        return True

    if verb not in READ_VERBS:
        return False
    flags = _WRITE_FLAGS.get(verb)
    if flags:
        if "*" in flags:
            return False
        if any(a == f or a.startswith(f) for a in args for f in flags):
            return False
    return True


def classify_command(command: str) -> str:
    """Return 'read' or 'write'. Conservative: anything unrecognized is 'write'."""
    # Command substitution can smuggle any verb — never classify it as read.
    if "$(" in command or "`" in command or "<(" in command or ">(" in command:
        return "write"
    tokens = _tokenize(command)
    if not tokens:
        return "write"
    # Redirections: any file-write redirect makes the whole command a write.
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        safe = _redirect_is_safe(tok, nxt)
        if safe is False:
            return "write"
    # Strip redirect tokens (+ their /dev/null targets) before segmenting.
    cleaned: list[str] = []
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        r = _redirect_is_safe(tok, nxt)
        if r is True:
            core = tok.lstrip("0123456789&").lstrip("<>&|")
            if not core and nxt is not None:   # bare '>' — target is the next token
                skip_next = True
            continue
        cleaned.append(tok)
    segments = _split_segments(cleaned)
    if not segments:
        return "write"
    return "read" if all(_segment_is_read(s) for s in segments) else "write"


# ---------------------------------------------------------------------------
# OS sandbox — kernel-level write denial for read-classified commands.

# macOS seatbelt profile: allow everything except file writes; /dev/null and the
# fd-duplication devices stay writable so `2>/dev/null`-style plumbing works.
_SEATBELT_PROFILE = (
    "(version 1)"
    "(allow default)"
    "(deny file-write*)"
    '(allow file-write-data (literal "/dev/null") (literal "/dev/stdout")'
    ' (literal "/dev/stderr") (literal "/dev/tty"))'
)


def sandbox_argv(command: str) -> list[str] | None:
    """argv that runs `command` under a deny-writes OS sandbox, or None when no
    sandbox is available on this platform (caller falls back to classifier-only)."""
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p", _SEATBELT_PROFILE, "/bin/sh", "-c", command]
    if system == "Linux" and shutil.which("bwrap"):
        return ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                "--tmpfs", "/tmp", "--die-with-parent", "/bin/sh", "-c", command]
    return None


def looks_sandbox_denied(output: str, exit_code: int) -> bool:
    """Heuristic: did this failure come from the sandbox blocking a write? Used to
    fall back to the approval prompt when a 'read'-classified command turned out
    to need write access."""
    if exit_code == 0:
        return False
    # Broad on purpose: a false positive here just means one extra approval
    # prompt (the command reruns unsandboxed after the user says yes).
    markers = ("operation not permitted", "read-only file system", "sandbox-exec",
               "deny file-write", "permission denied", "can't redirect",
               "cannot create", "can't create", "cannot open", "can't open")
    low = output.lower()
    return any(m in low for m in markers)
