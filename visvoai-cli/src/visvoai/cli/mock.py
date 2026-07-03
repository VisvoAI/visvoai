"""Mock data + environment probes for the UI foundation.

At integration time this module is replaced by real `visvoai-core` output; the
widgets that consume it do not change. `git_info()` is real (cheap, useful) and
likely survives into the product.
"""
from __future__ import annotations

import subprocess

THINKING_TEXT = (
    "The user wants an Anthropic provider in their config. I'll check the existing "
    "[model] block, then add a [providers.anthropic] section keyed off an env var "
    "so no secret lands in the file. Gemini stays the default."
)

# Markdown — the real shape of model output: a heading, prose with **bold** and
# `inline code`, a list, and a fenced code block (syntax-highlighted on render).
ASSISTANT_REPLY = """\
I'll add the **Anthropic** provider to your config. Here's the plan:

### Changes

- add a `[providers.anthropic]` block to `config.toml`
- key it off the `ANTHROPIC_API_KEY` env var (no secret in the file)
- leave **Gemini** as the default model

```toml
[providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"
default_model = "claude-opus-4-8"
```

Your existing Gemini default stays unchanged.
"""

# The showcase turn streams these in sequence so one message exercises every
# widget. INTRO is a short opener; SUMMARY is the markdown wrap-up.
ASSISTANT_INTRO = (
    "I'll add the **Anthropic** provider. Let me check the current `config.toml` "
    "first, then make the edit and run the provider tests."
)

ASSISTANT_SUMMARY = """\
Done — the **Anthropic** provider is wired up.

### What changed
- added `[providers.anthropic]` keyed off `ANTHROPIC_API_KEY`
- left **Gemini** (`gemini-2.5-flash`) as the default
- the provider tests pass (one cosmetic lint note, non-blocking)

You can switch to it any time with `/model`, or commit the change with `/commit`.
"""

# ── Rich showcase turn — "add rate limiting to the API" ──────────────────────
# A realistic multi-file feature build: explore → decide → implement → test (fail
# → fix → pass) → configure → summarize. Drives the live Plan tracker + every widget.

DEMO_PLAN: list[str] = [
    "Explore the API surface",
    "Choose a rate-limit backend",
    "Implement the middleware",
    "Wire config & run the tests",
    "Summarize & stage the commit",
]

THINKING_PLAN = (
    "Rate limiting belongs on the request path, so I'll add ASGI middleware rather "
    "than per-route decorators — that way every endpoint is covered without touching "
    "handlers. First I need to see how the app is wired and which framework it uses, "
    "then pick a backend: in-memory is fine for a single process; Redis only if they "
    "run multiple workers. Implement, test, and fold the limits into config so "
    "they're tunable without code changes."
)

CASE_B_THINK_OPEN = (
    "I can't reproduce a flaky test blindly — I need the specific CI failure. "
    "The stack trace will tell me which assertion is flaking and narrow the "
    "search to the code path that assertion exercises. Asking the user for the "
    "trace before reading any files."
)

THINKING_DIAGNOSE = (
    "The failing test expects a 429 with a Retry-After header, but my middleware "
    "returns 503 and no header. I'll map the limiter's rejection to 429 and compute "
    "Retry-After from the remaining window. Small fix in the reject path."
)

DIR_TREE: list[str] = [
    "api/",
    "  __init__.py",
    "  main.py              # FastAPI app + router includes",
    "  routes/",
    "    health.py",
    "    items.py",
    "  middleware/          # ← new home for the limiter",
    "  config.toml",
    "tests/",
    "  test_items.py",
    "  test_rate_limit.py   # ← currently failing (placeholder)",
]

GREP_RESULTS: list[str] = [
    'api/main.py:7:   app = FastAPI(title="items-api")',
    "api/main.py:9:   app.include_router(items.router)",
    "api/main.py:10:  app.include_router(health.router)",
    'api/routes/items.py:14:  @router.get("/items")',
]

MAIN_PY: list[str] = [
    "from fastapi import FastAPI",
    "from api.routes import items, health",
    "",
    'app = FastAPI(title="items-api")',
    "app.include_router(items.router)",
    "app.include_router(health.router)",
]

# (kind, code) diffs — syntax-highlighted per filename when rendered.
MIDDLEWARE_DIFF: list[tuple[str, str]] = [
    ("ctx", "from starlette.middleware.base import BaseHTTPMiddleware"),
    ("ctx", "from starlette.responses import Response"),
    ("add", "from time import monotonic"),
    ("add", ""),
    ("add", "class RateLimitMiddleware(BaseHTTPMiddleware):"),
    ("add", "    def __init__(self, app, limit: int, window: float):"),
    ("add", "        super().__init__(app)"),
    ("add", "        self.limit, self.window = limit, window"),
    ("add", "        self._hits: dict[str, list[float]] = {}"),
    ("add", ""),
    ("add", "    async def dispatch(self, request, call_next):"),
    ("add", "        key = request.client.host"),
    ("add", "        now = monotonic()"),
    ("add", "        hits = [t for t in self._hits.get(key, []) if now - t < self.window]"),
    ("add", "        if len(hits) >= self.limit:"),
    ("add", "            return Response(status_code=503)  # FIXME: should be 429"),
    ("add", "        hits.append(now)"),
    ("add", "        self._hits[key] = hits"),
    ("add", "        return await call_next(request)"),
]

MAIN_REGISTER_DIFF: list[tuple[str, str]] = [
    ("ctx", 'app = FastAPI(title="items-api")'),
    ("add", "from api.middleware.limiter import RateLimitMiddleware"),
    ("add", "app.add_middleware(RateLimitMiddleware, limit=100, window=60)"),
    ("ctx", "app.include_router(items.router)"),
]

MIDDLEWARE_FIX_DIFF: list[tuple[str, str]] = [
    ("ctx", "        if len(hits) >= self.limit:"),
    ("del", "            return Response(status_code=503)  # FIXME: should be 429"),
    ("add", "            retry = self.window - (now - hits[0])"),
    ("add", "            return Response(status_code=429,"),
    ("add", '                            headers={"Retry-After": str(int(retry))})'),
]

CONFIG_RATE_DIFF: list[tuple[str, str]] = [
    ("ctx", "[server]"),
    ("ctx", 'host = "0.0.0.0"'),
    ("add", ""),
    ("add", "[server.rate_limit]"),
    ("add", "requests = 100"),
    ("add", "window_seconds = 60"),
    ("add", "burst = 20"),
]

SHELL_FAIL: list[str] = [
    "$ pytest -q tests/test_rate_limit.py",
    "",
    "tests/test_rate_limit.py::test_allows_under_limit PASSED",
    "tests/test_rate_limit.py::test_blocks_over_limit FAILED",
    "",
    "=============================== FAILURES ===============================",
    "  assert response.status_code == 429",
    "  +  where 503 = <Response 503>.status_code",
    "",
    "1 failed, 1 passed in 0.41s",
]

SHELL_PASS: list[str] = [
    "$ pytest -q tests/test_rate_limit.py",
    "",
    "tests/test_rate_limit.py::test_allows_under_limit PASSED",
    "tests/test_rate_limit.py::test_blocks_over_limit PASSED",
    "tests/test_rate_limit.py::test_sets_retry_after PASSED",
    "",
    "3 passed in 0.52s",
]


async def gen_pytest_flaky_50():
    """Simulate `pytest --count=50` on the flaky test — 50 runs, ~30% flake.

    Mock-phase equivalent of iterating `subprocess.stdout`: yields one line per
    run on a timer (the caller paces the cadence)."""
    for i in range(1, 51):
        if i % 3 == 0 and i > 10:
            yield f"tests/test_checkout_concurrent.py::test_checkout_concurrent FAILED (run {i}/50)"
        else:
            yield f"tests/test_checkout_concurrent.py::test_checkout_concurrent PASSED (run {i}/50)"
    yield ""
    yield "23 passed, 27 failed in 52.3s"


def gen_ci_log(total: int = 2000, failures: int = 5) -> list[str]:
    """Generate a realistic CI log: mostly PASSED lines + scattered warnings, a
    handful of FAILED lines, and a traceback block near the end, capped with a
    summary. For exercising output tier-2 (search/save/jump-to-failure)."""
    # Spread failures evenly through the body, leaving room for the traceback.
    body = max(total - 8, 1)
    fail_at = {(i + 1) * body // (failures + 1) for i in range(failures)}
    lines: list[str] = []
    for i in range(body):
        if i in fail_at:
            lines.append(f"[{i:04d}] FAILED tests/test_mod_{i % 40}.py::test_case_{i}")
        elif i % 137 == 0:
            lines.append(f"[{i:04d}] WARNING deprecated call in module_{i % 40}")
        else:
            lines.append(f"[{i:04d}] PASSED tests/test_mod_{i % 40}.py::test_case_{i}")
    lines.extend([
        "Traceback (most recent call last):",
        '  File "tests/test_checkout_concurrent.py", line 47, in test_checkout',
        "    assert order.status == 'confirmed'",
        "AssertionError: connection pool exhausted under concurrency",
        "",
        f"{failures} failed, {body - failures} passed in 184.7s",
    ])
    return lines


CI_LOG_2000: list[str] = gen_ci_log(2000, 5)


# ── Case B Turn 4 — narrative (race condition) error ──────────────────────────
CASE_B_RACE_EXCERPT: list[str] = [
    "[gw3] test_checkout_concurrent.py::test_checkout_concurrent FAILED",
    "",
    "    conn = await pool.acquire(timeout=5)",
    "    cart = await checkout.create(conn, user_id, items)",
    ">   assert conn.amount is not None",
    "E   AttributeError: 'NoneType' object has no attribute 'amount'",
    "",
    "tests/test_checkout_concurrent.py:42: AttributeError",
]

CASE_B_RACE_ANNOTATION = (
    "Pool exhaustion under concurrency: the pool size is 5 but the test "
    "spawns 10 concurrent checkouts. The acquire timeout fires, returning "
    "None instead of a connection. Fix: raise pool size + add an acquire "
    "timeout guard."
)

CASE_E_STACK_EXCERPT: list[str] = [
    'File "checkout/service.py", line 142, in process_payment',
    "    amount = payment.amount * quantity",
    "AttributeError: 'NoneType' object has no attribute 'amount'",
    "",
    "  raised from:",
    "    checkout/deserializer.py:38: Payment.from_dict",
    "    api/routes/checkout.py:67: handle_checkout",
]

CASE_E_STACK_ANNOTATION = (
    "The payment field became nullable in yesterday's deploy (contract "
    "change in the payment gateway response). The deserializer at line 38 "
    "doesn't guard for None. One-line fix: add a null check before "
    "accessing .amount."
)


# ── Case B Turn 2 — multi-hop read chain ──────────────────────────────────────
# (tool_name, args, output_lines) — the 5-read debugging chain.
CASE_B_READ_CHAIN: list[tuple[str, str, list[str]]] = [
    ("read_file", "tests/test_checkout_concurrent.py", [
        "async def test_checkout_concurrent(pool, user_factory):",
        "    users = [user_factory() for _ in range(10)]",
        "    results = await asyncio.gather(*[checkout(u) for u in users])",
        "    assert all(r.success for r in results)",
    ]),
    ("read_file", "tests/conftest.py", [
        "@pytest.fixture",
        "async def pool():",
        "    return ConnectionPool(size=5, timeout=5)",
    ]),
    ("read_file", "tests/fixtures/pool.py", [
        "# Pool fixture helpers — looks suspicious but is fine.",
        "class ConnectionPool:",
        "    def __init__(self, size, timeout):",
        "        self.size, self.timeout = size, timeout",
    ]),
    ("read_file", "checkout/service.py", [
        "async def checkout(user):",
        "    conn = await pool.acquire(timeout=5)",
        "    cart = await create_cart(conn, user)",
        "    return await process_payment(conn, cart)",
    ]),
    ("read_file", "checkout/db.py", [
        "async def acquire(self, timeout):",
        "    try:",
        "        return await asyncio.wait_for(self._sem.acquire(), timeout)",
        "    except asyncio.TimeoutError:",
        "        return None  # ← the bug: returns None on timeout",
    ]),
]

# Indices of backtracks (dead ends) in the chain.
CASE_B_BACKTRACKS = [2]  # tests/fixtures/pool.py was a dead end


# ── Case B Turn 6 — interrupt + reconcile ─────────────────────────────────────
CASE_B_RECONCILE = {
    "context": "redirected after verification run 23/50",
    "kept": [
        "verification partial output (23/50 runs)",
        "flake reproduction note",
    ],
    "reverted": [
        "full suite re-run (narrowed to checkout tests)",
    ],
    "added": [
        "grep connection timeout settings",
        "verify timeout ≠ 0",
    ],
}

CASE_C_RECONCILE = {
    "context": "approach changed: offset → cursor pagination",
    "kept": [
        "route skeleton (routes/items.py)",
        "model params (page/size → cursor)",
    ],
    "reverted": [
        "offset query logic",
        "offset pagination tests",
    ],
    "added": [
        "cursor keyset query on id",
        "cursor pagination tests",
        "opaque token encoding",
    ],
}


# ── Case B Turn 4 — diagnosis (the race) ──────────────────────────────────────
CASE_B_DIAGNOSE_THINK = (
    "The pattern is clear from the CI log — failures cluster around concurrent "
    "checkout calls. The pool size is 5 but the test spawns 10 concurrent "
    "checkouts. When the pool exhausts, acquire() times out and returns None. "
    "The fix is twofold: raise the pool size and add a proper timeout guard "
    "that raises instead of returning None."
)

# ── Case B Turn 5 — hypothesis + fix ──────────────────────────────────────────
CASE_B_POOL_CONFIG: list[str] = [
    "[database]",
    "host = localhost",
    "port = 5432",
    "pool_size = 5",
    "pool_timeout = 5",
    "max_overflow = 0",
]

CASE_B_HYPOTHESIS_REPLY = (
    "Found it. The pool size is **5** but the test spawns **10** concurrent "
    "checkouts. When all 5 connections are in use, `acquire()` times out and "
    "returns `None` — which is the `AttributeError` we see. The fix: raise the "
    "pool size to 15 and make `acquire()` raise on timeout instead of returning "
    "`None`."
)

CASE_B_FIX_DIFF: list[tuple[str, str]] = [
    ("ctx", "    async def acquire(self, timeout):"),
    ("ctx", "        try:"),
    ("ctx", "            return await asyncio.wait_for(self._sem.acquire(), timeout)"),
    ("ctx", "        except asyncio.TimeoutError:"),
    ("del", "            return None"),
    ("add", "            raise ConnectionPoolExhausted("),
    ("add", '                f"Pool exhausted: {self.size} connections in use"'),
    ("add", "            )"),
]

# ── Case B Turn 6 — interrupt + redirect ──────────────────────────────────────
async def gen_pytest_verify_50():
    """Simulate the post-fix verification run — 50 runs, all passing."""
    for i in range(1, 51):
        yield (
            f"tests/test_checkout_concurrent.py::test_checkout_concurrent "
            f"PASSED (run {i}/50)"
        )
    yield ""
    yield "50 passed in 48.7s"


CASE_B_GREP_TIMEOUT: list[str] = [
    "tests/fixtures/pool.py:3:    timeout=0",
    "api/config.toml:5:pool_timeout = 5",
    "checkout/db.py:12:    acquire(timeout=self.timeout)",
]

CASE_B_TIMEOUT_FINDING = (
    "There's a second issue: `tests/fixtures/pool.py` sets `timeout=0`, which "
    "overrides the config's `pool_timeout = 5`. With a zero timeout, the pool "
    "never waits for a connection — it fails immediately. The fixture should "
    "use the config value, not hardcode zero."
)


DEMO_INTRO = (
    "I'll add **rate limiting** as ASGI middleware so it covers every route without "
    "touching the handlers. Here's my plan — I'll explore the app first, pick a "
    "backend with you, implement it, then make the limits configurable."
)

DEMO_BACKEND_TABLE = """\
Here are the backends worth considering:

| Backend    | Scope          | Extra deps    | Best when            |
| ---------- | -------------- | ------------- | -------------------- |
| In-memory  | single process | none          | one worker / dev     |
| Redis      | shared, multi  | `redis`       | many workers / prod  |
| Memcached  | shared, multi  | `pymemcache`  | existing memcached   |

For a single-process app, **in-memory** is the simplest correct choice.
"""

DEMO_SUMMARY = """\
Done — **rate limiting** is in and the suite is green. ✓

### Files changed
| File                          | Change                          |
| ----------------------------- | ------------------------------- |
| `api/middleware/limiter.py`   | new `RateLimitMiddleware`       |
| `api/main.py`                 | registered the middleware       |
| `api/config.toml`             | `[server.rate_limit]` settings  |

### Try it
```bash
for i in $(seq 1 120); do
  curl -s -o /dev/null -w "%{http_code}\\n" localhost:8000/items
done
# → 100×200, then 20×429 with a Retry-After header
```

Limits live in config, so you can tune them without code changes. Review and
commit with `/commit` whenever you're ready.
"""

DEMO_FORM_FIELDS: list[tuple[str, str, str]] = [
    ("requests", "Requests allowed", "100"),
    ("window", "Window (seconds)", "60"),
    ("burst", "Burst allowance", "20"),
]


# Mock contents returned by a `read_file` tool call.
FILE_READ: list[str] = [
    "[model]",
    'default = "gemini-2.5-flash"',
    "",
    "[providers.gemini]",
    'api_key_env = "GEMINI_API_KEY"',
]

# Mock stdout from a `run_shell` pytest call (long → collapsible).
SHELL_OUTPUT: list[str] = (
    ["$ pytest -q tests/test_providers.py", ""]
    + [f"tests/test_providers.py::test_case_{i:02d} PASSED" for i in range(1, 19)]
    + ["", "18 passed in 1.2s"]
)

# (kind, code) — kind in {"ctx", "add", "del"}; line numbers computed at render.
DIFF_CHANGES: list[tuple[str, str]] = [
    ("ctx", "[model]"),
    ("ctx", 'default = "gemini-2.5-flash"'),
    ("add", ""),
    ("add", "[providers.anthropic]"),
    ("add", 'api_key_env = "ANTHROPIC_API_KEY"'),
]


# A long fake command output to demo collapse/expand truncation.
LONG_OUTPUT: list[str] = [f"  test_module_{i:02d} ... ok" for i in range(1, 31)]

# A large fake diff to demo diff truncation.
BIG_DIFF: list[tuple[str, str]] = (
    [("ctx", "import os")]
    + [("add", f"line_{i} = {i}") for i in range(1, 26)]
    + [("ctx", "return result")]
)


# Fake past conversations for the sessions view (--resume / fork). At integration
# these come from ~/.visvoai/projects/<id>/conversations/. `when` is a pre-rendered
# relative string here; real data stores timestamps and renders relative at view.
import time as _time

_NOW = _time.time()
_DAY = 86400
# `_sort` (epoch seconds) drives recency grouping in SessionsScreen; computed from now so
# the demo always shows a realistic Today / Yesterday / Last 7 days / Last month / Older spread.
SESSIONS: list[dict] = [
    # Minutes ago, not hours — an hours offset crosses midnight in a late-night
    # run and "Today" vanishes from the recency grouping (calendar-day buckets).
    {"id": "a1c3", "title": "Add Anthropic provider to config", "when": "2h ago", "msgs": 14, "_sort": _NOW - 300},
    {"id": "b2d4", "title": "Fix the failing auth test", "when": "yesterday", "msgs": 31, "_sort": _NOW - 1 * _DAY},
    {"id": "c3e5", "title": "Investigate slow cold-start", "when": "3d ago", "msgs": 8, "_sort": _NOW - 3 * _DAY},
    {"id": "d4f6", "title": "Refactor the streaming pipeline", "when": "6d ago", "msgs": 52, "_sort": _NOW - 6 * _DAY},
    {"id": "e5a7", "title": "Add pytest fixtures for the sandbox", "when": "3w ago", "msgs": 19, "_sort": _NOW - 21 * _DAY},
    {"id": "f6b8", "title": "Wire up MinIO artifact previews", "when": "2mo ago", "msgs": 27, "_sort": _NOW - 60 * _DAY},
]

# Selectable models for the /model picker (mock; real list comes from visvoai-ai).
MODELS: list[tuple[str, str]] = [
    ("gemini-2.5-flash", "Gemini · fast default"),
    ("gemini-2.5-pro", "Gemini · deeper reasoning"),
    ("claude-opus-4-8", "Anthropic · most capable"),
    ("claude-sonnet-4-6", "Anthropic · balanced"),
]

# Mock git working-tree state for tests / `/demo`. The live `/commit` flow reads the
# real tree via `gitio.working_tree_status`; this fixture only feeds GitScreen's
# mock mode (cwd=None) for deterministic UI tests.
GIT_STATUS: dict = {
    "branch": "agent/add-anthropic-provider",
    "files": [
        {"path": "config.toml", "state": "M", "staged": True, "adds": 5, "dels": 1},
        {"path": "README.md", "state": "M", "staged": True, "adds": 3, "dels": 0},
        {"path": "tests/test_providers.py", "state": "A", "staged": False, "adds": 22, "dels": 0},
    ],
    "suggested_message": "Add Anthropic provider to config",
}


def git_info() -> str | None:
    """Return 'branch ✚N ~M -K' (staged/modified/untracked counts) for the cwd's
    git repo, or just 'branch' when clean, or None if not a repo."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=1,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=1,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=1
        ).stdout.splitlines()
        staged = sum(1 for ln in porcelain if ln[:1] not in (" ", "?", ""))
        modified = sum(1 for ln in porcelain if ln[1:2] not in (" ", ""))
        untracked = sum(1 for ln in porcelain if ln.startswith("??"))
        parts = []
        if staged:
            parts.append(f"✚{staged}")
        if modified:
            parts.append(f"~{modified}")
        if untracked:
            parts.append(f"…{untracked}")
        return f"{branch} | {' '.join(parts)}" if parts else branch
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
# Wave-2 case arcs (A / C / E / F / G). Mock data for the scripted /demo cases —
# replaced by real visvoai-core output at integration. Reuses CASE_E_STACK_*,
# CASE_C_RECONCILE, gen_ci_log, and the pytest generators above where possible.
# ════════════════════════════════════════════════════════════════════════════

# ── Case A — cross-module refactor: print() → structured logger ──────────────
CASE_A_THINK = (
    "Let me map every print() call site first, then refactor module by module so "
    "I can keep the suite green throughout. utils, routes, then the tests."
)
CASE_A_INTRO = (
    "I found **14 `print()` call sites across 9 files**. I'll migrate them to the "
    "structured `logger` in five steps, running the suite at the end.\n\n"
    "- `utils.py` — 3 sites\n- `routes/items.py`, `routes/health.py` — 6 sites\n"
    "- `tests/` — 5 sites"
)
CASE_A_PLAN = [
    "map all print() call sites",
    "refactor utils.py",
    "refactor routes/",
    "refactor tests/",
    "run the suite + verify",
]
CASE_A_GREP_PRINT = [
    "utils.py:12:    print(f\"loaded {name}\")",
    "utils.py:41:    print(\"cache miss\")",
    "utils.py:88:    print(err)",
    "routes/items.py:23:    print(\"listing items\")",
    "routes/health.py:9:    print(\"health ok\")",
    "… 9 more matches",
]
CASE_A_UTILS_DIFF = [
    ("ctx", "def load(name):"),
    ("del", '    print(f"loaded {name}")'),
    ("add", '    logger.info("loaded %s", name)'),
]
CASE_A_UTILS_DIFF2 = [
    ("del", '    print("cache miss")'),
    ("add", '    logger.debug("cache miss")'),
]
CASE_A_UTILS_DIFF3 = [
    ("del", "    print(err)"),
    ("add", '    logger.error("load failed: %s", err)'),
]
CASE_A_RESCAN_GREP = [
    "routes/_legacy.py:14:    print(\"deprecated path\")",
    "routes/_legacy.py:31:    print(resp)",
    "2 sites the first grep missed (hidden by a recursive import)",
]
CASE_A_ITEMS_DIFF = [
    ("del", '    print("listing items")'),
    ("add", '    logger.info("listing items")'),
]
CASE_A_TEST_FIX_DIFF = [
    ("ctx", "def test_load_logs(capsys):"),
    ("del", '    assert "loaded" in capsys.readouterr().out'),
    ("add", "    assert any('loaded' in r.message for r in caplog.records)"),
]
CASE_A_SUMMARY = (
    "Done — **16 sites across 11 files** now use `logger`. One test asserted on "
    "captured stdout; I switched it to `caplog`. Suite is green.\n\n"
    "Review the full change set with `/commit` (Ctrl+G)."
)

# ── Case C — feature build with mid-task redirection: pagination ─────────────
CASE_C_PLAN = [
    "read route + model",
    "add page/size params to the model",
    "add limit/offset to the route",
    "write pagination tests",
    "run the suite",
]
# route-after-model, tests-after-route — rendered as ordering hints.
CASE_C_DEPS = {2: 1, 3: 2}
CASE_C_PROPOSAL = (
    "Here's my plan for **offset pagination** (read-only so far — I won't edit "
    "until you unlock):\n\n"
    "- model: add `page` + `size` (validated, defaults 1/20)\n"
    "- route: translate to `LIMIT`/`OFFSET`\n"
    "- tests: first page, last page, out-of-range\n\n"
    "The model change must land before the route references it."
)
CASE_C_MODEL_DIFF = [
    ("add", "    page: int = Field(1, ge=1)"),
    ("add", "    size: int = Field(20, ge=1, le=100)"),
]
CASE_C_ROUTE_DIFF = [
    ("ctx", "@router.get('/items')"),
    ("add", "    offset = (q.page - 1) * q.size"),
    ("add", "    rows = session.query(Item).limit(q.size).offset(offset).all()"),
]
CASE_C_CURSOR_ROUTE_DIFF = [
    ("del", "    offset = (q.page - 1) * q.size"),
    ("del", "    rows = session.query(Item).limit(q.size).offset(offset).all()"),
    ("add", "    cur = decode_cursor(q.cursor)"),
    ("add", "    rows = session.query(Item).filter(Item.id > cur).limit(q.size).all()"),
]

# ── Case E — incident hotfix (reuses CASE_E_STACK_EXCERPT/ANNOTATION) ─────────
CASE_E_READ_CHAIN: list[tuple[str, str, list[str]]] = [
    ("read_file", "checkout/service.py:142", [
        "def finalize(order):",
        "    return charge(order.amount)   # amount is None",
    ]),
    ("read_file", "checkout/deserialize.py", [
        "def to_order(payload):",
        "    return Order(amount=payload['amount'])  # no guard",
    ]),
    ("read_file", "schemas/order_v2.py", [
        "amount: float | None  # became nullable in the v2 deploy",
    ]),
]
CASE_E_FIX_DIFF = [
    ("ctx", "def to_order(payload):"),
    ("del", "    return Order(amount=payload['amount'])"),
    ("add", "    amount = payload.get('amount')"),
    ("add", "    if amount is None:"),
    ("add", "        raise BadRequest('amount required')"),
    ("add", "    return Order(amount=amount)"),
]


async def gen_full_suite_then_break():
    """A full suite run that the user interrupts to narrow scope (Case E Turn 4)."""
    mods = ["auth", "billing", "checkout", "inventory", "orders", "users"]
    for i, m in enumerate(mods, 1):
        yield f"tests/test_{m}.py ... ok ({i}/{len(mods)} modules)"


async def gen_checkout_subset():
    """The narrowed run — just the checkout tests (Case E Turn 4)."""
    for i in range(1, 7):
        yield f"tests/test_checkout.py::test_case_{i} PASSED"
    yield ""
    yield "6 passed in 1.2s"


# ── Case F — greenfield scaffold ─────────────────────────────────────────────
CASE_F_LAYOUT = {
    "orders-service": {
        "app": {
            "main.py": None,
            "models": {"order.py": None},
            "routes": {"orders.py": None},
            "db.py": None,
            "config.py": None,
        },
        "migrations": {"0001_init.py": None},
        "tests": {"test_orders.py": None},
        "pyproject.toml": None,
        "README.md": None,
    }
}
# (path, content) in generation order: migration → model → route → config → tests → readme.
CASE_F_FILES: list[tuple[str, str]] = [
    ("app/db.py", "from sqlalchemy import create_engine\n\nengine = create_engine(DB_URL)\nSession = sessionmaker(engine)"),
    ("app/models/order.py", "class Order(Base):\n    __tablename__ = 'orders'\n    id = Column(Integer, primary_key=True)\n    total = Column(Numeric)"),
    ("app/routes/orders.py", "from app.models.order import Order\n\n@router.get('/orders')\ndef list_orders():\n    ..."),
    ("app/config.py", "class Settings(BaseSettings):\n    db_url: str\n    debug: bool = False"),
    ("tests/test_orders.py", "def test_list_orders(client):\n    assert client.get('/orders').status_code == 200"),
    ("README.md", "# orders-service\n\nRun: `uvicorn app.main:app --reload`"),
]
CASE_F_INTRO = (
    "I'll scaffold a FastAPI **orders** service. Two choices are open in the spec — "
    "the ORM and the database — so let me confirm those first."
)
CASE_F_SUMMARY = (
    "Scaffolded **8 files**. Run it with `uvicorn app.main:app --reload`.\n\n"
    "Next: fill in the order schema, then add auth. `/commit` to stage the scaffold."
)


async def gen_scaffold_install():
    """First-run: install deps then run the (empty) suite (Case F Turn 5)."""
    for pkg in ["fastapi", "sqlalchemy", "uvicorn", "pydantic", "pytest"]:
        yield f"Collecting {pkg} ..."
    yield "Successfully installed fastapi sqlalchemy uvicorn pydantic pytest"
    yield ""
    yield "tests/test_orders.py::test_list_orders PASSED"
    yield "1 passed in 0.4s"


# ── Case G — dependency major upgrade: SQLAlchemy 1.4 → 2.0 ───────────────────
CASE_G_CITATION = {
    "source": "SQLAlchemy 2.0 — What's New / Migration",
    "excerpt": ("Query.get() is legacy. Use Session.get(Model, pk).\n"
                "Query is superseded by select(); session.scalars(select(...)).all()."),
    "url": "docs.sqlalchemy.org/en/20/changelog/migration_20.html",
}
CASE_G_PLAN = [
    "Query.get → Session.get  (5 sites)",
    "Query.filter → select().filter  (9 sites)",
    "Query.all → session.scalars().all  (6 sites)",
    "relationship lazy-load fixes",
    "run the suite",
]
CASE_G_GREP = [
    "repo/users.py:18:    User.query.get(uid)",
    "repo/orders.py:42:    Order.query.filter(Order.open == True)",
    "repo/items.py:7:    Item.query.all()",
    "… 17 more Query. call sites across 7 files",
]
CASE_G_GET_DIFF = [
    ("del", "    return User.query.get(uid)"),
    ("add", "    return session.get(User, uid)"),
]
CASE_G_GET_DIFF2 = [
    ("del", "    return Order.query.get(oid)"),
    ("add", "    return session.get(Order, oid)"),
]
CASE_G_NARRATIVE_EXCERPT: list[str] = [
    "tests/test_orders.py::test_lazy_load FAILED",
    "    sqlalchemy.orm.exc.DetachedInstanceError: Instance <Order> is not",
    "    bound to a Session; lazy load operation cannot proceed",
]
CASE_G_NARRATIVE_ANNOTATION = (
    "2.0 flipped the default loading strategy — relationships no longer lazy-load "
    "after the session closes. The fix is an explicit `selectinload` on the query, "
    "per the migration guide. Patching the orders repo now."
)
CASE_G_REL_DIFF = [
    ("del", "    return session.scalars(select(Order)).all()"),
    ("add", "    return session.scalars(select(Order).options(selectinload(Order.items))).all()"),
]
# A suite run flooded with deprecation warnings mixed into the results.
CASE_G_WARN_FLOOD: list[str] = [
    "tests/test_users.py::test_get PASSED",
    "MovedIn20Warning: Query.get() is deprecated and will be removed",
    "tests/test_orders.py::test_list PASSED",
    "LegacyAPIWarning: The Query.filter() method is considered legacy",
    "RemovedIn20Warning: autoload=True is deprecated",
    "tests/test_items.py::test_all PASSED",
    "LegacyAPIWarning: Session.query() is considered legacy in 2.0",
    "DeprecationWarning: the 'bind' argument is deprecated",
    "tests/test_orders.py::test_lazy_load PASSED",
    "MovedIn20Warning: relationship lazy='dynamic' is superseded",
    "",
    "21 passed, 0 failed in 3.4s  ·  97 warnings",
]
CASE_G_SUMMARY = (
    "Upgrade complete — **20 `Query` sites across 7 files** migrated to 2.0 style, "
    "one lazy-load fixed with `selectinload`. Suite green (warnings are from "
    "third-party deps, not our code).\n\n"
    "**Watch for:** any raw `session.query(...)` in scripts outside the suite."
)
