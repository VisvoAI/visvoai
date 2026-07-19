"""Semantic tool retrieval — bind 8 relevant tools, not 300.

    pip install visvoai-core
    python 05_tool_retrieval.py            # runs with NO api key

THE PROBLEM this solves: connect a few MCP servers and you quickly hold
hundreds of tools. Binding them all wrecks the model — context bloat, worse
tool choice, higher cost. The fix is retrieval: index every tool once, then
per request bind only the handful that match the user's intent.

ToolCatalog is a BM25 index (a classic keyword-ranking algorithm — no
embeddings needed) over (name, description) — add per-tool
embeddings as a third tuple element and it becomes hybrid BM25 ∪ cosine.
This is the mechanism behind `per_round_retrieve` in the core graph, where
the bound tool set can be re-chosen every agent round.
"""
from visvoai.core.retrieval import ToolCatalog

# ── 1 · pretend we connected a few MCP servers: a big, mixed tool fleet ──────
# In real code you'd build this list from your servers' tools/list results
# (see build_catalog_from_servers) — (name, description) per tool.
FLEET = [
    ("github__create_issue",      "Create a new issue in a GitHub repository"),
    ("github__merge_pr",          "Merge a pull request"),
    ("github__list_workflows",    "List GitHub Actions workflows and their status"),
    ("slack__post_message",       "Post a message to a Slack channel"),
    ("slack__list_channels",      "List Slack channels in the workspace"),
    ("postgres__run_query",       "Run a read-only SQL query against Postgres"),
    ("postgres__describe_table",  "Show a table's columns, types and indexes"),
    ("chrome__take_screenshot",   "Screenshot the current browser page"),
    ("chrome__navigate",          "Navigate the browser to a URL"),
    ("chrome__lighthouse_audit",  "Run a Lighthouse performance audit on a page"),
    ("stripe__list_charges",      "List recent charges on the Stripe account"),
    ("stripe__refund_charge",     "Refund a Stripe charge by id"),
    ("jira__search_issues",       "Search Jira issues with JQL"),
    ("jira__transition_issue",    "Move a Jira issue to a new workflow state"),
    ("s3__list_objects",          "List objects in an S3 bucket"),
    ("s3__get_object",            "Download an object from S3"),
    # …imagine 300 of these
]

# ── 2 · index once ────────────────────────────────────────────────────────────
catalog = ToolCatalog(FLEET)

# ── 3 · per request: retrieve the relevant slice, bind only that ─────────────
for intent in [
    "why is the checkout page slow?",
    "refund the duplicate payment from yesterday",
    "what's in the orders table?",
]:
    picked = catalog.search(intent, k=4)
    print(f"{intent!r}\n    → bind: {picked}\n")

# In the real loop you'd now do:  model.bind_tools([tools_by_name[n] for n in picked])
# — the model sees 4 sharp options instead of 300 blurry ones. Names tokenize
# well ("chrome__lighthouse_audit" → chrome/lighthouse/audit), so even pure
# BM25 lands the right server's tools; embeddings sharpen it further.
