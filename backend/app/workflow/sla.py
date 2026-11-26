"""The decision timer (Stage 12 Part C, EDGE_CASES E-116 to E-118, E-129).

The officer decides within `SLA_WORKING_DAYS` working days of the report being ready. A working
day is Monday to Friday in `SLA_TIMEZONE` (public holidays are out of scope): the due time is the
report-ready time plus N x 24 hours of Monday-to-Friday time, so Friday 15:00 is due Tuesday 15:00
and Saturday 10:00 is due Wednesday 00:00.

Clock rules (E-117): only a case waiting for the officer (`awaiting_confirmation`) is timed. Each
report that waits sets a new due time (the Decision node, through `store.update_case`). A fix-type
stop and everything before submit are not timed; a reassignment keeps the due time; the officer's
decision stops the clock (no badge, no reminder).

Reminders (E-118): `check` runs inside the app every `SLA_CHECK_MINUTES` under an advisory lock,
like the retention job. The officer's notice goes when the case is overdue, the admins' one
working day after the due time. Each is claimed by one UPDATE keyed to the due time, so it goes
once per due time. No Celery, no Redis.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Engine, text

from app.notifications import inbox

log = logging.getLogger("loan_copilot.sla")
_LOCK = "hashtext('sla_check')"
DAY = timedelta(days=1)


@dataclass(frozen=True)
class SlaConfig:
    working_days: int = 2
    timezone: str = "Asia/Kolkata"

    @classmethod
    def from_settings(cls, settings: Any) -> "SlaConfig":
        return cls(settings.sla_working_days, settings.sla_timezone)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def due_at(self, ready: datetime) -> datetime:
        return add_working_time(ready, self.working_days * DAY, self.tz)


def _next_weekday_start(local: datetime) -> datetime:
    """Midnight starting the next Monday-to-Friday day after `local`'s date."""
    day = local.date() + DAY
    while day.weekday() >= 5:  # Saturday, Sunday
        day += DAY
    return datetime.combine(day, time(0), tzinfo=local.tzinfo)


def add_working_time(start: datetime, amount: timedelta, tz: ZoneInfo) -> datetime:
    """`start` plus `amount` of Monday-to-Friday time in `tz`, returned in UTC (E-116)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    now = start.astimezone(tz)
    if now.weekday() >= 5:  # the clock starts on the next working day
        now = _next_weekday_start(now)
    left = amount
    while True:
        day_end = datetime.combine(now.date() + DAY, time(0), tzinfo=tz)
        if now + left <= day_end:
            return (now + left).astimezone(UTC)
        left -= day_end - now
        now = _next_weekday_start(now)


def due_state_sql(tz_param: str = ":sla_tz") -> str:
    """One SQL expression for the badge, used by every list and the export: 'overdue' once the due
    time has passed, 'due_today' when it falls on today's date in the bank's time zone, else
    NULL. Only a case waiting for the officer is timed."""
    return f"""CASE WHEN c.status = 'awaiting_confirmation' AND c.sla_due_at IS NOT NULL THEN
                 CASE WHEN c.sla_due_at <= now() THEN 'overdue'
                      WHEN (c.sla_due_at AT TIME ZONE {tz_param})::date
                           = (now() AT TIME ZONE {tz_param})::date THEN 'due_today' END END"""


# --- the check ------------------------------------------------------------------------------
@dataclass
class CheckReport:
    filled: int = 0  # waiting cases given a due time (cases already waiting when 0027 arrived)
    officer: int = 0
    admin: int = 0


def _fill_missing(conn: Connection, cfg: SlaConfig, now: datetime, report: CheckReport) -> None:
    """A case already waiting when the timer arrived gets its due time from its report-ready
    time. One already past it is marked as told, so an upgrade does not send a burst of old
    reminders; its Overdue badge still shows (E-129)."""
    rows = conn.execute(
        text("""SELECT id, report_ready_at FROM cases
                WHERE status = 'awaiting_confirmation' AND sla_due_at IS NULL
                  AND report_ready_at IS NOT NULL""")
    ).all()
    for r in rows:
        due = cfg.due_at(r.report_ready_at)
        told = due if due <= now else None
        conn.execute(
            text("""UPDATE cases SET sla_due_at = :d, sla_officer_notified_for = :t,
                        sla_admin_notified_for = :t WHERE id = :c AND sla_due_at IS NULL"""),
            {"d": due, "t": told, "c": r.id},
        )  # fmt: skip
        report.filled += 1


def _remind_officers(conn: Connection, now: datetime, report: CheckReport) -> None:
    claimed = conn.execute(
        text("""UPDATE cases c SET sla_officer_notified_for = c.sla_due_at
                WHERE c.status = 'awaiting_confirmation' AND c.sla_due_at <= :now
                  AND c.sla_officer_notified_for IS DISTINCT FROM c.sla_due_at
                RETURNING c.id, c.case_no, c.created_by"""),
        {"now": now},
    ).all()
    for r in claimed:
        active = conn.execute(
            text("SELECT active FROM users WHERE id = :u"), {"u": r.created_by}
        ).scalar()
        ref = inbox.CaseRef(r.id, r.case_no)
        if active and inbox.notify(conn, r.created_by, "case_overdue", ref):
            report.officer += 1


def _remind_admins(conn: Connection, cfg: SlaConfig, now: datetime, report: CheckReport) -> None:
    rows = conn.execute(
        text("""SELECT id, case_no, sla_due_at FROM cases
                WHERE status = 'awaiting_confirmation' AND sla_due_at <= :now
                  AND sla_admin_notified_for IS DISTINCT FROM sla_due_at"""),
        {"now": now},
    ).all()
    for r in rows:
        if add_working_time(r.sla_due_at, DAY, cfg.tz) > now:
            continue  # not yet a working day past its due time
        won = conn.execute(
            text("""UPDATE cases SET sla_admin_notified_for = sla_due_at
                    WHERE id = :c AND status = 'awaiting_confirmation'
                      AND sla_admin_notified_for IS DISTINCT FROM sla_due_at RETURNING id"""),
            {"c": r.id},
        ).first()  # fmt: skip
        if won:
            report.admin += inbox.notify_admins(conn, "case_overdue_admin",
                                                inbox.CaseRef(r.id, r.case_no))  # fmt: skip


def check(engine: Engine, cfg: SlaConfig, now: datetime | None = None) -> CheckReport | None:
    """One pass. Returns None when another process holds the lock (it is checking there)."""
    now = now or datetime.now(UTC)
    report = CheckReport()
    with engine.begin() as conn:
        if not conn.execute(text(f"SELECT pg_try_advisory_xact_lock({_LOCK})")).scalar():
            return None
        _fill_missing(conn, cfg, now, report)
        _remind_officers(conn, now, report)
        _remind_admins(conn, cfg, now, report)
    return report


async def run_worker(engine: Engine, cfg: SlaConfig, every_minutes: int) -> None:
    """The loop started with the app. A failure is logged and the loop goes on."""
    while True:
        try:
            done = await asyncio.to_thread(check, engine, cfg)
            if done is not None and (done.officer or done.admin or done.filled):
                log.info("decision timer check", extra={"sla": done.__dict__})
        except Exception as exc:  # noqa: BLE001 - the loop must survive a bad moment
            log.error("decision timer check failed: %s", type(exc).__name__)
        await asyncio.sleep(every_minutes * 60)
