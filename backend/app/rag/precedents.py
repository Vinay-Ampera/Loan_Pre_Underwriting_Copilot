"""Approved-precedent retrieval for the Policy agent.

A precedent is used only for a refer-band case, with the same loan type, status approved, not
expired, and similarity at or above the rules-file threshold. A case that stopped on a hard rule
gets none. Precedents never change a hard rule; the capped bonus is applied by the scoring code.
Precedents are written by the Stage 7 learning loop; this module only reads them.
"""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import Connection, text

from app.rag.config import load_rag_config
from app.rag.embedder import embed_passages
from app.rag.schemas import PrecedentMatch
from app.scoring.rules import RuleSet

SEARCH_SQL = text(
    """SELECT id, report_summary, final_decision,
              1 - (embedding <=> CAST(:q AS vector)) AS similarity
       FROM precedents
       WHERE status = 'approved' AND loan_type = :lt AND valid_until >= :today
             AND embedding IS NOT NULL
       ORDER BY embedding <=> CAST(:q AS vector)
       LIMIT :n"""
)


def precedent_text(loan_type: str, rule_ids: Iterable[str], band: str) -> str:
    """The text that is embedded for both a stored precedent and a new case. No personal data."""
    return f"{loan_type} loan, {band} band. Rules involved: {', '.join(sorted(set(rule_ids)))}."


def find_precedents(
    conn: Connection,
    *,
    loan_type: str,
    band: str | None,
    rule_ids: Iterable[str],
    hard_failed: bool,
    ruleset: RuleSet,
    today: date | None = None,
) -> list[PrecedentMatch]:
    if hard_failed or band != "refer":
        return []
    query = embed_passages([precedent_text(loan_type, rule_ids, band)])[0]
    rows = conn.execute(
        SEARCH_SQL,
        {"q": str(query), "lt": loan_type, "today": today or date.today(),
         "n": load_rag_config().precedent_candidates},
    ).all()  # fmt: skip
    floor = ruleset.precedent.similarity_min
    return [
        PrecedentMatch(
            id=str(r.id),
            similarity=round(float(r.similarity), 4),
            summary=r.report_summary,
            final_decision=r.final_decision,
        )
        for r in rows
        if r.similarity >= floor
    ]
