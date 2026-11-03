"""Who decided what on a case, and which decision is in force.

The chain is system recommendation, then the officer (`officer_actions`), then any admin
corrections (`admin_actions`). Nothing is replaced: the latest admin row is the decision in
force, and the officer's row stays visible beneath it. An admin may correct only a case the
officer has already decided, and never one that failed a hard rule (locked decision 2).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

DECIDED = ("confirmed", "overridden")
# the officer has not decided yet and nothing is running: the admin may hand the case on
REASSIGNABLE = ("draft", "uploaded", "stopped", "awaiting_confirmation")
HARD_RULE_TEXT = "This case failed a hard rule, which an admin cannot override."


def admin_actions(conn: Connection, case_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("""SELECT a.action, a.previous_decision, a.final_decision, a.reason, a.created_at,
                       u.name AS admin
                FROM admin_actions a JOIN users u ON u.id = a.admin_id
                WHERE a.case_id = :c ORDER BY a.created_at, a.id"""), {"c": case_id})  # fmt: skip
    return [{"action": r.action, "previous_decision": r.previous_decision,
             "final_decision": r.final_decision, "reason": r.reason, "at": r.created_at,
             "admin": r.admin} for r in rows]  # fmt: skip


def decision_in_force(conn: Connection, case_id: UUID) -> str | None:
    """approve | refer | reject: the latest admin correction, else the officer's decision."""
    admin = conn.execute(
        text("""SELECT final_decision FROM admin_actions WHERE case_id = :c
                ORDER BY created_at DESC, id DESC LIMIT 1"""), {"c": case_id}).scalar()  # fmt: skip
    if admin is not None:
        return str(admin)
    officer = conn.execute(
        text("""SELECT final_decision FROM officer_actions WHERE case_id = :c
                ORDER BY created_at DESC, id DESC LIMIT 1"""), {"c": case_id}).scalar()  # fmt: skip
    return None if officer is None else str(officer)


def failed_hard_rule(row: Any, report: dict[str, Any] | None) -> bool:
    """A stop on a hard rule, a failed hard rule, or a cap to refer, as the report records it."""
    if row.stop_class is not None:
        return True
    findings = (report or {}).get("findings", [])
    return any(f.get("severity") in ("hard_fail", "cap") for f in findings)


def override_block(row: Any, report: dict[str, Any] | None) -> str | None:
    """Why an admin cannot correct this case now, or None."""
    if row.status not in DECIDED:
        return "The admin corrects a case only after the officer has decided it."
    if failed_hard_rule(row, report):
        return HARD_RULE_TEXT
    return None
