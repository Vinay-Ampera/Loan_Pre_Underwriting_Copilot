"""Retrieval evaluation: `python -m app.rag.evaluate --split dev [--write-baseline]`.

Runs every query in data/rag/retrieval_eval.yaml through vector search alone (the baseline) and
through vector search plus rerank, and reports hit@1, recall@1/3/5 and MRR for each. Citation
validity checks that every returned clause exists in the policy files, belongs to the common
policy or the query's loan type, and is on the active version; it must be 100%.

Process: record the vector-only baseline first (`--write-baseline`), then set the targets in
data/rag/baseline.json after looking at it. The command exits non-zero when a target is missed.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

import yaml
from sqlalchemy import Connection, create_engine

from app.core.config import REPO_ROOT, get_settings
from app.rag.config import load_rag_config
from app.rag.policy_loader import load_all
from app.rag.retrieve import PolicyRetriever
from app.rag.schemas import RetrievedClause

EVAL_PATH = REPO_ROOT / "data" / "rag" / "retrieval_eval.yaml"
BASELINE_PATH = REPO_ROOT / "data" / "rag" / "baseline.json"
KS = (1, 3, 5)


@dataclass(frozen=True)
class Query:
    id: str
    split: str
    loan_type: str
    query: str
    expected: list[str]


def load_queries(split: str) -> list[Query]:
    raw = yaml.safe_load(EVAL_PATH.read_text(encoding="utf-8"))["queries"]
    return [Query(**q) for q in raw if split in ("all", q["split"])]


def score_query(expected: list[str], returned: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in KS:
        found = len(set(expected) & set(returned[:k]))
        out[f"recall@{k}"] = found / len(expected)
        out[f"hit@{k}"] = 1.0 if found else 0.0
    rank = next((i + 1 for i, cid in enumerate(returned) if cid in expected), None)
    out["mrr"] = 1.0 / rank if rank else 0.0
    return out


def citation_validity(hits: list[RetrievedClause], loan_type: str, known: dict[str, str]) -> float:
    """Share of returned clauses that exist in the policy files, fit the loan type, are active."""
    if not hits:
        return 1.0
    ok = sum(
        1
        for h in hits
        if known.get(h.clause_id) == h.doc_loan_type
        and h.doc_loan_type in ("common", loan_type)
        and h.active
    )
    return ok / len(hits)


def evaluate(conn: Connection, queries: list[Query], rerank: bool) -> dict[str, float]:
    retriever = PolicyRetriever(conn)
    known = {c.clause_id: d.loan_type for d in load_all() for c in d.clauses}
    sums: dict[str, float] = {}
    validity: list[float] = []
    for q in queries:
        hits = retriever.search(q.query, q.loan_type, top_k=max(KS), rerank=rerank)
        for name, value in score_query(q.expected, [h.clause_id for h in hits]).items():
            sums[name] = sums.get(name, 0.0) + value
        validity.append(citation_validity(hits, q.loan_type, known))
    n = len(queries)
    metrics = {name: round(v / n, 4) for name, v in sums.items()}
    metrics["citation_validity"] = round(sum(validity) / n, 4)
    metrics["queries"] = float(n)
    return metrics


def check_targets(metrics: dict[str, float], targets: dict[str, float]) -> list[str]:
    return [
        f"{name}: {metrics.get(name, 0.0):.4f} < target {t:.4f}"
        for name, t in targets.items()
        if metrics.get(name, 0.0) < t
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--write-baseline", action="store_true", help="store vector-only metrics")
    args = ap.parse_args()

    queries = load_queries(args.split)
    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.connect() as conn:
        baseline = evaluate(conn, queries, rerank=False)
        reranked = evaluate(conn, queries, rerank=True)

    cfg = load_rag_config()
    print(
        f"split={args.split} queries={len(queries)} top_k={cfg.top_k} candidates={cfg.candidates}"
    )
    print(f"{'metric':20}{'vector only':>14}{'+ rerank':>12}")
    for name in [
        *(f"hit@{k}" for k in KS),
        *(f"recall@{k}" for k in KS),
        "mrr",
        "citation_validity",
    ]:
        print(f"{name:20}{baseline[name]:>14.4f}{reranked[name]:>12.4f}")

    stored: dict[str, Any] = (
        json.loads(BASELINE_PATH.read_text()) if BASELINE_PATH.exists() else {"targets": {}}
    )
    if args.write_baseline:
        stored["baseline_dev"] = baseline
        stored["baseline_dev_with_rerank"] = reranked
        BASELINE_PATH.write_text(json.dumps(stored, indent=2) + "\n")
        print(f"baseline written to {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return

    failures = check_targets(reranked, stored.get("targets", {}))
    if reranked["citation_validity"] < 1.0:
        failures.append("citation_validity below 1.0")
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("targets met")


if __name__ == "__main__":
    main()
