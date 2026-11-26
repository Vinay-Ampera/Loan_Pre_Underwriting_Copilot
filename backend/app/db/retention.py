"""Retention job (SECURITY.md 7, DATABASE.md 8). Runs once a day inside the app
(`RETENTION_HOURS`, no scheduler, no Celery) and by hand:

    python -m app.db.retention [--dry-run]

1. **Bureau-derived data**, `BUREAU_RETENTION_MONTHS` (6) after a case was created (v1 has no
   consent renewal): the stored values of the rules that read the bureau (credit score, days
   past due, enquiries) are removed from `rule_results.evidence` and from the findings in the
   case's reports (the PDF is drawn from the report on request, so it follows). The pass or
   fail, the points and the written finding stay: they are the record of the decision (RBI asks
   for written reasons). Once the officer has decided, the run's LangGraph checkpoints, which
   hold the whole bureau record, are deleted and the case is stamped `bureau_removed_at`.
2. **Staff email**, `EMAIL_RETENTION_DAYS` (90): `email_outbox` rows that are no longer queued.
3. **Chat turns**, `CHAT_RETENTION_DAYS` (90): `case_chat_messages` rows (an answer may quote the
   credit score, so they go well inside the bureau limit).

Each run that changes something writes one `retention_run` audit row with counts only. Two app
processes never run it at once (an advisory lock).
"""

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from app.api.deps import write_audit
from app.scoring.rules import RuleSet, load_rules

log = logging.getLogger("loan_copilot.retention")

BUREAU_FIELDS = frozenset({"cibil_score", "bureau_dpd_max_12m", "enquiries_6m"})
REMOVED = "removed by the retention job (bureau data is kept six months)"
DECIDED = ("confirmed", "overridden")
_LOCK = "hashtext('retention_job')"
_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


@dataclass
class RetentionReport:
    cases: int = 0
    rule_results: int = 0
    reports: int = 0
    checkpoints: int = 0
    emails: int = 0
    chats: int = 0

    @property
    def changed(self) -> bool:
        return any(asdict(self).values())


def bureau_rule_ids(rs: RuleSet) -> list[str]:
    return sorted({r.rule_id for r in rs.rules if r.field in BUREAU_FIELDS})


def _clean_report(data: dict[str, Any], ids: set[str]) -> bool:
    changed = False
    facts = data.get("facts") or {}  # the figures kept for the case chat
    for block in [facts.get("case") or {}, *(facts.get("persons") or [])]:
        for name in BUREAU_FIELDS & set(block):
            del block[name]
            changed = True
    for f in data.get("findings") or []:
        if f.get("rule_id") in ids and f.get("evidence") != {"removed": REMOVED}:
            f["evidence"] = {"removed": REMOVED}
            changed = True
    return changed


def _checkpoint_tables(conn: Connection) -> list[str]:
    exists = text("SELECT to_regclass(:t)")
    return [t for t in _CHECKPOINT_TABLES if conn.execute(exists, {"t": f"langgraph.{t}"}).scalar()]


def remove_bureau_data(
    conn: Connection, rs: RuleSet, months: int, report: RetentionReport, *, dry_run: bool = False
) -> None:  # fmt: skip
    ids = bureau_rule_ids(rs)
    cases = conn.execute(
        text("""SELECT id, status FROM cases
                WHERE created_at < now() - make_interval(months => :m)
                  AND bureau_removed_at IS NULL AND status <> 'running'
                ORDER BY created_at"""),
        {"m": months},
    ).all()  # fmt: skip
    tables = _checkpoint_tables(conn)
    for case in cases:
        report.cases += 1
        if dry_run:
            continue
        report.rule_results += conn.execute(
            text("""UPDATE rule_results rr
                    SET evidence = jsonb_build_object('role', rr.evidence -> 'role',
                                                      'removed', CAST(:msg AS text))
                    FROM stage_runs s
                    WHERE rr.stage_run_id = s.id AND s.case_id = :c
                      AND rr.rule_id = ANY(CAST(:ids AS text[]))
                      AND NOT (rr.evidence ? 'removed')"""),
            {"c": case.id, "ids": ids, "msg": REMOVED},
        ).rowcount  # fmt: skip
        for row in conn.execute(
            text("SELECT id, report_json FROM reports WHERE case_id = :c"), {"c": case.id}
        ).all():
            data = dict(row.report_json or {})
            if _clean_report(data, set(ids)):
                conn.execute(
                    text("UPDATE reports SET report_json = CAST(:j AS jsonb) WHERE id = :i"),
                    {"j": json.dumps(data), "i": row.id},
                )
                report.reports += 1
        if case.status in DECIDED:
            for t in tables:
                report.checkpoints += conn.execute(
                    text(f"DELETE FROM langgraph.{t} WHERE thread_id = :t"),  # noqa: S608 - fixed names
                    {"t": str(case.id)},
                ).rowcount  # fmt: skip
            conn.execute(text("UPDATE cases SET bureau_removed_at = now() WHERE id = :c"),
                         {"c": case.id})  # fmt: skip


def remove_old_email(
    conn: Connection, days: int, report: RetentionReport, *, dry_run: bool = False
) -> None:
    where = "status <> 'queued' AND created_at < now() - make_interval(days => :d)"
    verb = "SELECT count(*)" if dry_run else "DELETE"
    result = conn.execute(text(f"{verb} FROM email_outbox WHERE {where}"), {"d": days})  # noqa: S608
    report.emails += int(result.scalar_one()) if dry_run else result.rowcount


def remove_old_chat(
    conn: Connection, days: int, report: RetentionReport, *, dry_run: bool = False
) -> None:
    where = "created_at < now() - make_interval(days => :d)"
    verb = "SELECT count(*)" if dry_run else "DELETE"
    result = conn.execute(text(f"{verb} FROM case_chat_messages WHERE {where}"), {"d": days})  # noqa: S608
    report.chats += int(result.scalar_one()) if dry_run else result.rowcount


def run(engine: Engine, rs: RuleSet, *, months: int = 6, email_days: int = 90,
        chat_days: int = 90, dry_run: bool = False) -> RetentionReport | None:  # fmt: skip
    """One pass. Returns None when another process holds the lock (it is running there)."""
    report = RetentionReport()
    with engine.begin() as conn:
        if not conn.execute(text(f"SELECT pg_try_advisory_xact_lock({_LOCK})")).scalar():
            return None
        remove_bureau_data(conn, rs, months, report, dry_run=dry_run)
        remove_old_email(conn, email_days, report, dry_run=dry_run)
        remove_old_chat(conn, chat_days, report, dry_run=dry_run)
        if report.changed and not dry_run:
            after = {**asdict(report), "months": months, "email_days": email_days,
                     "chat_days": chat_days}  # fmt: skip
            write_audit(conn, None, "retention_run", "system", None, after=after)
    return report


async def run_worker(engine: Engine, rs: RuleSet, every_hours: int, months: int,
                     email_days: int, chat_days: int = 90) -> None:  # fmt: skip
    """The daily loop started with the app. A failure is logged and the loop goes on."""
    while True:
        try:
            done = await asyncio.to_thread(
                run, engine, rs, months=months, email_days=email_days, chat_days=chat_days
            )
            if done is not None and done.changed:
                log.info("retention run", extra={"retention": asdict(done)})
        except Exception as exc:  # noqa: BLE001 - the loop must survive a bad moment
            log.error("retention run failed: %s", type(exc).__name__)
        await asyncio.sleep(every_hours * 3600)


def main() -> None:
    from app.core.config import get_settings  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Remove data past its retention period.")
    ap.add_argument("--dry-run", action="store_true", help="count only, change nothing")
    args = ap.parse_args()
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_url())
    try:
        out = run(engine, load_rules(), months=settings.bureau_retention_months,
                  email_days=settings.email_retention_days,
                  chat_days=settings.chat_retention_days, dry_run=args.dry_run)  # fmt: skip
    finally:
        engine.dispose()
    if out is None:
        print("Another process is running the retention job; nothing done.")
        return
    word = "would change" if args.dry_run else "changed"
    print(f"Retention {word}: " + ", ".join(f"{k} {v}" for k, v in asdict(out).items()))


if __name__ == "__main__":
    main()
