"""
visvoai.core.retrieval — Tool retrieval for Plan A dynamic binding.

ToolCatalog is a BM25 + optional cosine-hybrid retrieval index over
(name, description) tool documents. It is the core mechanism that lets
the agent bind only the subset of tools relevant to the current query
instead of overwhelming the LLM with every available tool upfront.

Platform surfaces add a per-tool embedding to entries, enabling the HYBRID
(BM25 ∪ cosine) pool; without embeddings the catalog falls back to BM25 only.

Usage:
    entries = [("tool_name", "what it does"), ...]
    catalog = ToolCatalog(entries)
    relevant = catalog.search("user intent query", k=8)
"""
import math
import re
from typing import Dict, List, Optional, Tuple

# Split on non-alphanumerics AND camelCase / snake boundaries so
# "kaggle__search_datasets" and "searchDatasets" both tokenize to
# ["kaggle", "search", "datasets"].
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]+")


def _tokenize(text: str) -> List[str]:
    text = _CAMEL.sub(" ", text or "")
    return [t for t in _NON_ALNUM.split(text.lower()) if t]


class ToolCatalog:
    """BM25 index over (name, description) documents. One document per tool.

    Pass an embedding (L2-normalized float list) as the third element of each
    entry to enable hybrid BM25+cosine retrieval. Without embeddings the
    catalog uses BM25 only.
    """

    K1 = 1.5
    B = 0.75

    def __init__(self, entries: List[Tuple]) -> None:
        """
        entries: list of (name, description) OR (name, description, embedding).
        The name is tokenized into the BM25 document as well — tool names are
        highly informative for lexical retrieval.
        embedding: optional L2-normalized float list; enables the cosine pool.
        """
        self.names: List[str] = []
        self._docs: List[List[str]] = []
        self._embeddings: List[Optional[List[float]]] = []

        for entry in entries:
            name, description = entry[0], entry[1]
            embedding = entry[2] if len(entry) > 2 else None
            self.names.append(name)
            self._docs.append(_tokenize(name) + _tokenize(description))
            self._embeddings.append(embedding)

        self._has_embeddings = any(e for e in self._embeddings)
        self._n = len(self._docs)
        self._avg_len = (sum(len(d) for d in self._docs) / self._n) if self._n else 0.0

        self._df: Dict[str, int] = {}
        self._tf: List[Dict[str, int]] = []
        for doc in self._docs:
            tf: Dict[str, int] = {}
            for term in doc:
                tf[term] = tf.get(term, 0) + 1
            self._tf.append(tf)
            for term in tf:
                self._df[term] = self._df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        # BM25 idf with +0.5 smoothing; floor at 0 so common terms don't go negative.
        return max(0.0, math.log((self._n - df + 0.5) / (df + 0.5) + 1.0))

    def _score(self, query_terms: List[str], idx: int) -> float:
        tf = self._tf[idx]
        dl = len(self._docs[idx])
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = self._idf(term)
            denom = f + self.K1 * (1 - self.B + self.B * (dl / self._avg_len if self._avg_len else 0))
            score += idf * (f * (self.K1 + 1)) / denom
        return score

    def _bm25_ranked(self, query: str) -> List[int]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        scored = [(self._score(query_terms, i), i) for i in range(self._n)]
        scored = [(s, i) for s, i in scored if s > 0.0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored]

    def _cosine_ranked(self, query_vec: List[float]) -> List[int]:
        """Rank by cosine similarity (L2-normalized vectors → dot product)."""
        sims = []
        for i, e in enumerate(self._embeddings):
            if not e:
                continue
            sims.append((sum(a * b for a, b in zip(query_vec, e)), i))
        sims.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in sims]

    def search(self, query: str, k: int = 8, query_vec: Optional[List[float]] = None) -> List[str]:
        """Return up to k tool names most relevant to query.

        BM25 only when no query_vec or no embeddings. Otherwise HYBRID via
        DUAL-POOL UNION: top-k BM25 ∪ top-k cosine. Union (not RRF) so a
        strong semantic hit binds even when BM25 buries it under lexically-
        similar names. Never worse than BM25: BM25's top-k is always included.
        """
        if self._n == 0 or k <= 0:
            return []
        bm = self._bm25_ranked(query)
        if query_vec is None or not self._has_embeddings:
            return [self.names[i] for i in bm[:k]]
        cos = self._cosine_ranked(query_vec)
        out: List[int] = []
        for i in bm[:k]:
            out.append(i)
        for i in cos[:k]:
            if i not in out:
                out.append(i)
        return [self.names[i] for i in out]


def build_catalog_from_servers(servers: List) -> ToolCatalog:
    """Build a ToolCatalog from server objects with a .tools attribute.

    Entry name is namespaced as "{server_name}__{tool_name}".
    Compatible with both MCPServerDefinition objects (platform) and any
    object that has .name and .tools[] with .name / .description attributes.
    """
    entries: List[Tuple] = []
    for server in servers:
        for tool in getattr(server, "tools", []) or []:
            name = f"{server.name}__{tool.name}"
            entries.append((
                name,
                getattr(tool, "description", "") or "",
                getattr(tool, "embedding", None),
            ))
    return ToolCatalog(entries)
