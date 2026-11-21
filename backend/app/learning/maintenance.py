"""Keeping the precedent store honest after it is built (Stage 10c, Learnings).

  pause_for_policy  a policy change touched a clause one of a precedent's rules points at: the
                    precedent stops counting until the admin confirms it again or retires it
  reconfirm         the admin puts a paused precedent back (only while it has not expired)
  retire            the admin takes an approved or paused precedent out early
  record_use        one row each time a precedent's bonus reached a case
  learnings         what the store holds, with how often and where each one was used

Nothing here edits a precedent's summary or its rules: they were approved as written. Every
change is written to the audit log with the reason.
"""

import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.scoring.rules import RuleSet

LOANS = ("personal", "home", "education", "business", "vehicle")
LEARNING_STATUSES = ("approved", "paused", "retired", "expired")


class LearningError(ValueError):
    """A request the precedent's state does not allow (the API turns it into a 409)."""


def _audit(conn: Connection, actor: UUID | None, action: str, pid: Any, before: dict[str, Any],
           after: dict[str, Any]) -> None:  # fmt: skip
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, before, after)
                VALUES (:u, :a, 'precedent', :e, CAST(:b AS jsonb), CAST(:f AS jsonb))"""),
        {"u": actor, "a": action, "e": str(pid), "b": json.dumps(before, default=str),
         "f": json.dumps(after, default=str)},
    )  # fmt: skip


def pause_for_policy(
    conn: Connection, loan_type: str, clause_ids: set[str], rules: RuleSet, version: str
) -> list[str]:
    """Pause approved precedents whose rules cite a changed or removed clause. Returns their ids."""
    rule_ids = sorted({r.rule_id for r in rules.rules if r.policy_clause in clause_ids})
    if not rule_ids:
        return []
    types = list(LOANS) if loan_type == "common" else [loan_type]
    why = f"The {loan_type} policy changed (version {version}) in a clause one of its rules uses."
    rows = conn.execute(
        text("""UPDATE precedents SET status = 'paused', paused_at = now(), paused_reason = :why
                WHERE status = 'approved' AND loan_type = ANY(:t)
                      AND rule_ids && CAST(:r AS text[])
                RETURNING id"""),
        {"why": why, "t": types, "r": rule_ids},
    ).all()  # fmt: skip
    ids = [str(r.id) for r in rows]
    for pid in ids:
        _audit(conn, None, "precedent_paused", pid, {"status": "approved"},
               {"status": "paused", "policy": loan_type, "version": version})  # fmt: skip
    return ids


def _locked(conn: Connection, pid: UUID) -> Any:
    row = conn.execute(
        text("SELECT id, status, valid_until FROM precedents WHERE id = :i FOR UPDATE"), {"i": pid}
    ).first()
    if row is None:
        raise LookupError("Precedent not found.")
    return row


def reconfirm(
    conn: Connection, pid: UUID, actor: UUID, reason: str, today: date | None = None
) -> dict[str, Any]:
    row = _locked(conn, pid)
    if row.status != "paused":
        raise LearningError(
            f"This precedent is {row.status}; only a paused one can be confirmed again."
        )
    if row.valid_until is None or row.valid_until < (today or date.today()):
        raise LearningError(
            "This precedent has expired, so it cannot be confirmed again. Retire it."
        )
    conn.execute(
        text("""UPDATE precedents SET status = 'approved', paused_at = NULL, paused_reason = NULL
                WHERE id = :i"""),
        {"i": pid},
    )
    _audit(conn, actor, "precedent_reconfirmed", pid, {"status": "paused"},
           {"status": "approved", "reason": reason})  # fmt: skip
    return {"id": str(pid), "status": "approved"}


def retire(conn: Connection, pid: UUID, actor: UUID, reason: str) -> dict[str, Any]:
    row = _locked(conn, pid)
    if row.status not in ("approved", "paused"):
        raise LearningError(
            f"This precedent is {row.status}; only an approved or paused one can be retired."
        )
    conn.execute(
        text("""UPDATE precedents SET status = 'retired', retired_by = :u, retired_at = now(),
                    retired_reason = :why
                WHERE id = :i"""),
        {"u": actor, "why": reason, "i": pid},
    )  # fmt: skip
    _audit(conn, actor, "precedent_retired", pid, {"status": row.status},
           {"status": "retired", "reason": reason})  # fmt: skip
    return {"id": str(pid), "status": "retired"}


def record_use(conn: Connection, pid: str, case_id: Any, bonus: float) -> None:
    conn.execute(
        text("UPDATE precedents SET times_used = times_used + 1 WHERE id = :i"), {"i": pid}
    )
    conn.execute(
        text("INSERT INTO precedent_uses (precedent_id, case_id, bonus) VALUES (:p, :c, :b)"),
        {"p": pid, "c": case_id, "b": bonus},
    )


def learnings(conn: Connection, status: str = "all", today: date | None = None) -> dict[str, Any]:
    """Approved, paused, retired and expired precedents with their use, and the counts."""
    today = today or date.today()
    rows = conn.execute(
        text("""SELECT p.id, p.status, p.loan_type, p.rule_ids, p.final_decision,
                       p.report_summary, p.valid_until, p.times_used, p.reviewed_at,
                       p.paused_reason, p.paused_at, p.retired_reason, p.retired_at,
                       ru.name AS reviewed_by, tu.name AS retired_by,
                       (SELECT max(used_at) FROM precedent_uses u WHERE u.precedent_id = p.id) AS last_used,
                       (SELECT coalesce(array_agg(x.case_no ORDER BY x.used_at DESC), '{}')
                          FROM (SELECT c.case_no, u.used_at FROM precedent_uses u
                                JOIN cases c ON c.id = u.case_id
                                WHERE u.precedent_id = p.id ORDER BY u.used_at DESC LIMIT 5) x) AS cases
                FROM precedents p LEFT JOIN users ru ON ru.id = p.reviewed_by
                     LEFT JOIN users tu ON tu.id = p.retired_by
                WHERE p.status IN ('approved', 'paused', 'retired', 'expired')
                ORDER BY p.reviewed_at DESC NULLS LAST LIMIT 300"""),
    ).all()  # fmt: skip
    items = []
    for r in rows:
        shown = (
            "expired"
            if r.status in ("approved", "paused") and r.valid_until and r.valid_until < today
            else r.status
        )
        if status != "all" and shown != status:
            continue
        items.append({
            "id": str(r.id), "status": shown, "loan_type": r.loan_type, "rule_ids": list(r.rule_ids),
            "final_decision": r.final_decision, "summary": r.report_summary,
            "valid_until": r.valid_until, "days_left": (r.valid_until - today).days if r.valid_until else None,
            "times_used": r.times_used, "last_used": r.last_used, "cases": list(r.cases or []),
            "reviewed_by": r.reviewed_by, "reviewed_at": r.reviewed_at,
            "paused_reason": r.paused_reason, "paused_at": r.paused_at,
            "retired_reason": r.retired_reason, "retired_at": r.retired_at, "retired_by": r.retired_by,
        })  # fmt: skip
    counts = dict.fromkeys(("pending", "held", *LEARNING_STATUSES, "rejected"), 0)
    for r in conn.execute(
        text("""SELECT CASE WHEN status IN ('approved', 'paused') AND valid_until < :d
                            THEN 'expired' ELSE status END AS s, count(*) AS n
                FROM precedents GROUP BY 1"""),
        {"d": today},
    ):  # fmt: skip
        counts[r.s] = counts.get(r.s, 0) + r.n
    month = conn.execute(
        text("SELECT count(*) FROM precedent_uses WHERE used_at > now() - interval '30 days'")
    ).scalar_one()
    return {"items": items, "counts": counts, "uses_30d": month}
