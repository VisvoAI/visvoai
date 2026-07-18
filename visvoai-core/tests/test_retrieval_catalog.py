"""ToolCatalog: the retrieval quality contract (BM25 + hybrid + tokenizing)."""
from visvoai.core.retrieval import ToolCatalog, make_per_round_retrieve

FLEET = [
    ("github__create_issue", "Create a new issue in a GitHub repository"),
    ("slack__post_message", "Post a message to a Slack channel"),
    ("postgres__run_query", "Run a read-only SQL query against Postgres"),
    ("postgres__describe_table", "Show a table's columns, types and indexes"),
    ("chrome__lighthouse_audit", "Run a Lighthouse performance audit on a page"),
    ("stripe__refund_charge", "Refund a Stripe charge by id"),
]


def test_intent_ranks_the_right_server_first():
    cat = ToolCatalog(FLEET)
    assert cat.search("refund the duplicate payment", k=2)[0] == "stripe__refund_charge"
    assert cat.search("why is the page slow", k=2)[0] == "chrome__lighthouse_audit"
    top = cat.search("what columns does the orders table have", k=2)
    assert top[0] == "postgres__describe_table"


def test_tool_names_tokenize_camel_and_snake():
    """Names are documents too: 'kaggle__searchDatasets' must match 'search
    datasets' via camel/snake splitting."""
    cat = ToolCatalog([("kaggle__searchDatasets", "find data"),
                       ("other__thing", "unrelated")])
    assert cat.search("search datasets", k=1) == ["kaggle__searchDatasets"]


def test_k_bounds_and_empty_query():
    cat = ToolCatalog(FLEET)
    assert len(cat.search("table", k=3)) <= 3
    assert cat.search("", k=4) == []           # nothing to rank on


def test_hybrid_embeddings_extend_the_bm25_pool():
    """With embeddings, a lexically-unrelated but vector-near tool joins the
    pool (BM25 ∪ cosine)."""
    # 2-d toy embeddings: axis 0 = "payments", axis 1 = "browsers"
    entries = [
        ("stripe__refund_charge", "Refund a charge", [1.0, 0.0]),
        ("chrome__navigate", "Open a URL", [0.0, 1.0]),
        ("billing__adjust_invoice", "totally different words", [1.0, 0.0]),
    ]
    cat = ToolCatalog(entries)
    got = cat.search("refund the charge", k=3, query_vec=[1.0, 0.0])
    assert "billing__adjust_invoice" in got     # cosine pulled it in
    got_lex_only = ToolCatalog([e[:2] for e in entries]).search("refund the charge", k=3)
    assert "billing__adjust_invoice" not in got_lex_only


def test_make_per_round_retrieve_is_graph_ready():
    retrieve = make_per_round_retrieve(ToolCatalog(FLEET), k=2)
    out = retrieve("post an update to slack")
    assert out[0] == "slack__post_message"
    assert isinstance(out, list) and all(isinstance(n, str) for n in out)
