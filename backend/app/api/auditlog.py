"""The audit log as the admin and the auditor read it: one query, filters, paging and CSV.

The admin sees the stored entries as they are. The auditor sees the same entries with identifiers
masked and no case ids (the auditor has no case access). Reading never writes anything.
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any

from fastapi import Response
from sqlalchemy import Connection, text

from app.api import display

CSV_LIMIT = 5000


def _where(
    action: str | None, entity: str | None, actor: str | None, case_no: str | None,
    date_from: date | None, date_to: date | None,
) -> tuple[str, dict[str, Any]]:  # fmt: skip
    where = """(CAST(:a AS text) IS NULL OR l.action = :a)
               AND (CAST(:e AS text) IS NULL OR l.entity = :e)
               AND (CAST(:u AS uuid) IS NULL OR l.actor_id = CAST(:u AS uuid))
               AND (CAST(:c AS text) IS NULL OR c.case_no ILIKE '%' || :c || '%')
               AND (CAST(:f AS date) IS NULL OR l.at >= CAST(:f AS date))
               AND (CAST(:t AS date) IS NULL OR l.at < CAST(:t AS date))"""
    params = {"a": action or None, "e": entity or None, "u": actor or None,
              "c": (case_no or "").strip() or None, "f": date_from,
              "t": None if date_to is None else date_to + timedelta(days=1)}  # fmt: skip
    return where, params


_FROM = """FROM audit_log l LEFT JOIN users u ON u.id = l.actor_id
           LEFT JOIN cases c ON l.entity = 'case' AND c.id::text = l.entity_id"""


def query(
    conn: Connection, *, auditor: bool, action: str | None = None, entity: str | None = None,
    actor: str | None = None, case_no: str | None = None, date_from: date | None = None,
    date_to: date | None = None, limit: int = 100, offset: int = 0,
) -> dict[str, Any]:  # fmt: skip
    where, params = _where(action, entity, actor, case_no, date_from, date_to)
    rows = conn.execute(
        text(f"""SELECT l.at, l.action, l.entity, l.before, l.after, u.name AS actor,
                        u.role AS actor_role, c.case_no, c.id AS case_id
                 {_FROM} WHERE {where} ORDER BY l.at DESC, l.id LIMIT :n OFFSET :o"""),  # noqa: S608
        {**params, "n": limit, "o": offset},
    ).all()
    total = conn.execute(
        text(f"SELECT count(*) {_FROM} WHERE {where}"),
        params,  # noqa: S608
    ).scalar_one()

    def shown(value: Any) -> Any:
        return display.scrub_for_auditor(value, []) if auditor else value

    return {"total": total, "rows": [
        {"at": r.at, "action": r.action, "entity": r.entity, "case_no": r.case_no,
         "case_id": None if auditor else r.case_id,
         "actor": r.actor or "System", "actor_role": r.actor_role,
         "before": shown(r.before), "after": shown(r.after)}
        for r in rows
    ]}  # fmt: skip


def actions(conn: Connection) -> list[str]:
    return [
        r.action for r in conn.execute(text("SELECT DISTINCT action FROM audit_log ORDER BY 1"))
    ]


def _cell(value: object) -> str:
    """A spreadsheet runs text that starts with = + - or @ as a formula; keep it text."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def csv_response(name: str, header: Sequence[str], rows: Iterable[Sequence[object]]) -> Response:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for r in rows:
        w.writerow([_cell(v) for v in r])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "private, no-store"})  # fmt: skip


def log_csv(result: dict[str, Any], name: str) -> Response:
    return csv_response(
        name, ["When", "Actor", "Role", "Action", "Case", "Detail"],
        [[r["at"], r["actor"], r["actor_role"], r["action"], r["case_no"],
          r["after"] if r["after"] is not None else r["before"]] for r in result["rows"]],
    )  # fmt: skip
