"""Policy retrieval: pgvector search, cross-encoder rerank, metadata filters.

Filters: the policy versions in force, and only the common policy plus the case's loan type.
"In force" is the set the run bound when it started (`app/rag/versions.py`), or the set given as
`docs` (the knowledge base swaps a draft in to preview it), or else the active versions. A clause
is marked `active` when its version is in that set, which is what the grounding check reads.
`relevance` is the rerank score (0..1); with `rerank=False` it is the cosine similarity, which is
the baseline the retrieval evaluation compares against.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import Connection, Row, text

from app.rag import versions
from app.rag.config import RagConfig, load_rag_config
from app.rag.embedder import embed_query, rerank_scores
from app.rag.schemas import RetrievedClause

EmbedQuery = Callable[[str], list[float]]
Rerank = Callable[[str, list[str]], list[float]]

_IN_FORCE = "(CASE WHEN CAST(:docs AS uuid[]) IS NULL THEN d.active ELSE d.id = ANY(CAST(:docs AS uuid[])) END)"
SEARCH_SQL = text(
    f"""SELECT c.clause_id, c.text, c.metadata, d.loan_type, d.version, {_IN_FORCE} AS active,
              1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
       FROM policy_chunks c JOIN policy_documents d ON d.id = c.policy_document_id
       WHERE {_IN_FORCE} AND d.loan_type = ANY(:types) AND c.embedding IS NOT NULL
       ORDER BY c.embedding <=> CAST(:q AS vector)
       LIMIT :n"""
)
BY_ID_SQL = text(
    f"""SELECT c.clause_id, c.text, c.metadata, d.loan_type, d.version, {_IN_FORCE} AS active
       FROM policy_chunks c JOIN policy_documents d ON d.id = c.policy_document_id
       WHERE {_IN_FORCE} AND d.loan_type = ANY(:types) AND c.clause_id = ANY(:ids)"""
)


def allowed_types(loan_type: str) -> list[str]:
    return ["common", loan_type]


class PolicyRetriever:
    def __init__(
        self,
        conn: Connection,
        config: RagConfig | None = None,
        embed: EmbedQuery = embed_query,
        rerank_fn: Rerank = rerank_scores,
        docs: dict[str, str] | None = None,
    ) -> None:
        self.conn = conn
        self.cfg = config or load_rag_config()
        self._embed = embed
        self._rerank = rerank_fn
        self.docs = docs  # loan type -> policy_documents.id; None = the run's bound set

    def _docs(self) -> list[str] | None:
        docs = self.docs if self.docs is not None else versions.bound()
        return None if docs is None else sorted(docs.values())

    def search(
        self,
        query: str,
        loan_type: str,
        *,
        top_k: int | None = None,
        candidates: int | None = None,
        rerank: bool = True,
    ) -> list[RetrievedClause]:
        k = top_k or self.cfg.top_k
        rows = self.conn.execute(
            SEARCH_SQL,
            {"q": str(self._embed(query)), "types": allowed_types(loan_type),
             "n": candidates or self.cfg.candidates, "docs": self._docs()},
        ).all()  # fmt: skip
        rows = [r for r in rows if r.similarity >= self.cfg.min_vector_similarity]
        if not rows:
            return []
        if rerank:
            scores = self._rerank(query, [r.text for r in rows])
            relevance = scores
        else:
            relevance = [float(r.similarity) for r in rows]
        hits = [
            _clause(r, rel, float(r.similarity), "search")
            for r, rel in zip(rows, relevance, strict=True)
        ]
        hits.sort(key=lambda h: h.relevance, reverse=True)
        if rerank:
            hits = [h for h in hits if h.relevance >= self.cfg.min_relevance]
        return hits[:k]

    def by_ids(self, clause_ids: list[str], loan_type: str) -> list[RetrievedClause]:
        """Clauses a rule points at, fetched directly (relevance 1.0, via='rule')."""
        if not clause_ids:
            return []
        rows = self.conn.execute(
            BY_ID_SQL,
            {
                "types": allowed_types(loan_type),
                "ids": sorted(set(clause_ids)),
                "docs": self._docs(),
            },
        ).all()
        return [_clause(r, 1.0, None, "rule") for r in rows]


def _clause(row: Row[Any], relevance: float, sim: float | None, via: str) -> RetrievedClause:
    r = row._mapping
    meta = r["metadata"] or {}
    return RetrievedClause(
        clause_id=r["clause_id"],
        title=meta.get("title", ""),
        text=r["text"],
        source_tag=meta.get("source_tag", "sample"),
        doc_loan_type=r["loan_type"],
        doc_version=r["version"],
        active=bool(r["active"]),
        relevance=relevance,
        vector_similarity=sim,
        via="rule" if via == "rule" else "search",
    )


def merge(*groups: list[RetrievedClause]) -> list[RetrievedClause]:
    """Union by clause_id, keeping the highest relevance; rule-linked clauses win ties."""
    best: dict[str, RetrievedClause] = {}
    for group in groups:
        for c in group:
            cur = best.get(c.clause_id)
            if cur is None or (c.relevance, c.via == "rule") > (cur.relevance, cur.via == "rule"):
                best[c.clause_id] = c
    return sorted(best.values(), key=lambda c: (-c.relevance, c.clause_id))
