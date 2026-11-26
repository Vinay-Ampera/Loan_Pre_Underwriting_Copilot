"""The decision timer (Stage 12 Part C): working-day maths, the clock rules, the reminders and
migration 0027 (EDGE_CASES E-116 to E-118, E-129)."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import Connection, Engine, create_engine, text

from app.agents import store
from app.db.migrate import alembic_config
from app.notifications.check import check_notification_text
from app.notifications.inbox import KINDS
from app.workflow import sla
from app.workflow.sla import SlaConfig, add_working_time

IST = ZoneInfo("Asia/Kolkata")
CFG = SlaConfig(2, "Asia/Kolkata")


def ist(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=IST)


# --- working days (pure) --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ready", "due"),
    [
        (ist(2026, 11, 23, 10), ist(2026, 11, 25, 10)),  # Monday 10:00 -> Wednesday 10:00
        (ist(2026, 11, 26, 10), ist(2026, 11, 30, 10)),  # Thursday -> Monday, over the weekend
        (ist(2026, 11, 27, 15), ist(2026, 12, 1, 15)),  # Friday 15:00 -> Tuesday 15:00
        (ist(2026, 11, 28, 10), ist(2026, 12, 2, 0)),  # Saturday: the clock starts Monday 00:00
        (ist(2026, 11, 29, 23, 30), ist(2026, 12, 2, 0)),  # Sunday night likewise
        (ist(2026, 11, 27, 23, 50), ist(2026, 12, 1, 23, 50)),  # Friday 23:50 India time
    ],
)  # fmt: skip
def test_due_time_counts_monday_to_friday_only(ready: datetime, due: datetime) -> None:
    got = CFG.due_at(ready.astimezone(UTC))  # stored in UTC, counted in India time
    assert got == due and got.tzinfo == UTC


def test_a_naive_time_is_read_as_utc_and_one_working_day_is_the_admin_wait() -> None:
    friday_late = datetime(2026, 11, 27, 18, 20)  # 23:50 in India, no time zone attached
    assert CFG.due_at(friday_late) == ist(2026, 12, 1, 23, 50)
    assert add_working_time(ist(2026, 11, 27, 15), timedelta(days=1), IST) == ist(2026, 11, 30, 15)


# --- the database ---------------------------------------------------------------------------
@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    yield eng
    eng.dispose()


def user(conn: Connection, name: str, role: str, *, active: bool = True,
         emails: bool = True) -> Any:  # fmt: skip
    return conn.execute(
        text("""INSERT INTO users (name, email, password_hash, role, active, notice_emails)
                VALUES (:n, :e, 'x', :r, :a, :m) RETURNING id"""),
        {"n": name, "e": f"{name.split()[0].lower()}@example.test", "r": role, "a": active,
         "m": emails},
    ).scalar_one()  # fmt: skip


def case(conn: Connection, owner: Any, no: int, status: str = "awaiting_confirmation",
         due: datetime | None = None, ready: datetime | None = None) -> Any:  # fmt: skip
    return conn.execute(
        text("""INSERT INTO cases (case_no, loan_type, created_by, status, sla_due_at,
                    report_ready_at) VALUES (:n, 'personal', :o, :s, :d, :r) RETURNING id"""),
        {"n": f"CASE-2026-{no:04d}", "o": owner, "s": status, "d": due, "r": ready},
    ).scalar_one()  # fmt: skip


def notices(conn: Connection, kind: str | None = None) -> list[Any]:
    return list(conn.execute(
        text("""SELECT n.kind, u.name, n.case_ref FROM notifications n JOIN users u ON u.id = n.user_id
                WHERE CAST(:k AS text) IS NULL OR n.kind = :k ORDER BY u.name"""),
        {"k": kind},
    ))  # fmt: skip


def due_state(conn: Connection, case_id: Any) -> str | None:
    return conn.execute(  # type: ignore[no-any-return]
        text(f"SELECT {sla.due_state_sql()} FROM cases c WHERE c.id = :c"),
        {"c": case_id, "sla_tz": "Asia/Kolkata"},
    ).scalar()


def test_due_state_is_for_a_waiting_case_only(engine: Engine) -> None:
    now = datetime.now(UTC)
    today_end = datetime.combine(now.astimezone(IST).date() + timedelta(days=1), datetime.min.time(), IST)  # fmt: skip
    with engine.begin() as c:
        o = user(c, "Asha Officer", "officer")
        late = case(c, o, 1, due=now - timedelta(minutes=1))
        later_today = case(c, o, 2, due=today_end - timedelta(seconds=1))
        tomorrow = case(c, o, 3, due=today_end + timedelta(seconds=1))
        decided = case(c, o, 4, status="confirmed", due=now - timedelta(days=3))
        stopped = case(c, o, 5, status="stopped", due=now - timedelta(days=3))
        assert due_state(c, late) == "overdue"
        if now < today_end - timedelta(seconds=2):  # not in the last two seconds of the day
            assert due_state(c, later_today) == "due_today"
        assert due_state(c, tomorrow) is None
        assert due_state(c, decided) is None and due_state(c, stopped) is None  # E-117


def test_each_waiting_report_restarts_the_clock_and_a_stop_is_not_timed(engine: Engine) -> None:
    with engine.begin() as c:
        cid = case(c, user(c, "Asha Officer", "officer"), 1, status="running")
        store.update_case(c, cid, "awaiting_confirmation", sla=CFG)
        first = c.execute(text("SELECT sla_due_at, report_ready_at FROM cases WHERE id = :c"),
                          {"c": cid}).one()  # fmt: skip
        assert first.sla_due_at == CFG.due_at(first.report_ready_at)
        c.execute(text("UPDATE cases SET sla_due_at = sla_due_at - interval '9 days' WHERE id = :c"),
                  {"c": cid})  # fmt: skip
        store.update_case(c, cid, "stopped")  # a fix-type stop on a re-run: not timed
        assert due_state(c, cid) is None
        store.update_case(c, cid, "awaiting_confirmation", sla=CFG)  # a new report
        again = c.execute(text("SELECT sla_due_at FROM cases WHERE id = :c"), {"c": cid}).scalar()
        assert again > datetime.now(UTC) and due_state(c, cid) is None  # a fresh clock
        store.update_case(c, cid, "confirmed")  # the decision stops it
        assert due_state(c, cid) is None
        kept = c.execute(text("SELECT sla_due_at FROM cases WHERE id = :c"), {"c": cid}).scalar()
        assert kept == again  # history stays; only a waiting case is timed


def test_reminders_go_once_to_the_owner_then_to_every_admin_a_working_day_later(
    engine: Engine,
) -> None:
    now = datetime.now(UTC)
    with engine.begin() as c:
        asha = user(c, "Asha Officer", "officer")
        user(c, "Ada Admin", "admin")
        user(c, "Ann Admin", "admin")
        user(c, "Aud Auditor", "auditor")
        user(c, "Old Admin", "admin", active=False)
        due = now - timedelta(minutes=5)
        cid = case(c, asha, 1, due=due)
        case(c, asha, 2, status="confirmed", due=now - timedelta(days=5))  # decided first: none
    first = sla.check(engine, CFG, now)
    assert first is not None and (first.officer, first.admin) == (1, 0)
    with engine.connect() as c:
        assert [(n.kind, n.name, n.case_ref) for n in notices(c)] == [
            ("case_overdue", "Asha Officer", "CASE-2026-0001")]  # fmt: skip
    assert sla.check(engine, CFG, now) is not None  # a second pass sends nothing
    with engine.connect() as c:
        assert len(notices(c)) == 1

    almost = add_working_time(due, timedelta(days=1), IST) - timedelta(minutes=1)
    assert sla.check(engine, CFG, almost).admin == 0  # type: ignore[union-attr]
    later = add_working_time(due, timedelta(days=1), IST) + timedelta(minutes=1)
    assert sla.check(engine, CFG, later).admin == 2  # type: ignore[union-attr]
    assert sla.check(engine, CFG, later).admin == 0  # type: ignore[union-attr]
    with engine.connect() as c:
        admins = [n.name for n in notices(c, "case_overdue_admin")]
        assert admins == ["Ada Admin", "Ann Admin"]  # never the auditor or a disabled admin
        assert c.execute(text("SELECT sla_officer_notified_for = sla_due_at AND sla_admin_notified_for "
                              "= sla_due_at FROM cases WHERE id = :c"), {"c": cid}).scalar()  # fmt: skip


def test_a_restarted_clock_reminds_again_and_a_disabled_owner_gets_none(engine: Engine) -> None:
    now = datetime.now(UTC)
    with engine.begin() as c:
        asha = user(c, "Asha Officer", "officer")
        gone = user(c, "Gone Officer", "officer", active=False)
        cid = case(c, asha, 1, due=now - timedelta(hours=1))
        case(c, gone, 2, due=now - timedelta(hours=1))
    sla.check(engine, CFG, now)
    with engine.begin() as c:
        assert [n.name for n in notices(c, "case_overdue")] == ["Asha Officer"]
        claimed = c.execute(text("SELECT count(*) FROM cases WHERE sla_officer_notified_for IS NOT NULL")).scalar()  # fmt: skip
        assert claimed == 2  # the disabled officer's case is claimed, so it is not retried
        c.execute(
            text("UPDATE cases SET sla_due_at = :d WHERE id = :c"),
            {"d": now - timedelta(minutes=1), "c": cid},
        )  # a new report, already late
    sla.check(engine, CFG, now)
    with engine.connect() as c:
        assert [n.name for n in notices(c, "case_overdue")] == ["Asha Officer", "Asha Officer"]


def test_the_lock_keeps_two_checks_from_running_together(engine: Engine) -> None:
    now = datetime.now(UTC)
    with engine.begin() as c:
        case(c, user(c, "Asha Officer", "officer"), 1, due=now - timedelta(hours=1))
    with engine.begin() as holder:  # another process is checking
        holder.execute(text("SELECT pg_advisory_xact_lock(hashtext('sla_check'))"))
        assert sla.check(engine, CFG, now) is None
    assert sla.check(engine, CFG, now).officer == 1  # type: ignore[union-attr]


def test_the_notice_email_follows_the_persons_switch(engine: Engine) -> None:
    now = datetime.now(UTC)
    with engine.begin() as c:
        on = user(c, "Asha Officer", "officer", emails=True)
        off = user(c, "Ben Officer", "officer", emails=False)
        case(c, on, 1, due=now - timedelta(hours=1))
        case(c, off, 2, due=now - timedelta(hours=1))
    sla.check(engine, CFG, now)
    with engine.connect() as c:
        sent = [r[0] for r in c.execute(text(
            "SELECT u.name FROM email_outbox e JOIN users u ON u.id = e.user_id WHERE e.kind = 'notice'"))]  # fmt: skip
        assert sent == ["Asha Officer"] and len(notices(c, "case_overdue")) == 2


def test_cases_waiting_before_the_timer_get_a_due_time_but_no_old_reminders(engine: Engine) -> None:
    now = datetime.now(UTC)
    with engine.begin() as c:
        asha = user(c, "Asha Officer", "officer")
        old = case(c, asha, 1, ready=now - timedelta(days=20))  # long past its due time
        fresh = case(c, asha, 2, ready=now - timedelta(minutes=5))
    report = sla.check(engine, CFG, now)
    assert report is not None and report.filled == 2 and report.officer == 0
    with engine.connect() as c:
        rows = {r.id: r for r in c.execute(text(
            "SELECT id, sla_due_at, sla_officer_notified_for, report_ready_at FROM cases"))}  # fmt: skip
        assert rows[old].sla_due_at == CFG.due_at(rows[old].report_ready_at)
        assert rows[old].sla_officer_notified_for == rows[old].sla_due_at  # E-129: no burst
        assert rows[fresh].sla_officer_notified_for is None
        assert due_state(c, old) == "overdue" and notices(c) == []


def test_the_overdue_texts_are_fixed_and_carry_no_number_or_outcome() -> None:
    for key in ("case_overdue", "case_overdue_admin"):
        k = KINDS[key]
        assert check_notification_text(f"{k.title}\n{k.body}") == []
        assert not re.search(r"\d", k.title + k.body) and k.target == "case"
    assert KINDS["case_overdue"].roles == ("officer",)
    assert KINDS["case_overdue_admin"].roles == ("admin",)


def test_migration_0027_adds_the_timer_and_the_kinds_and_rolls_back(clean_db_url: str) -> None:
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "0027")
    eng = create_engine(clean_db_url)

    def kinds(c: Connection) -> set[str]:
        sql = "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'notifications_kind_check'"
        return set(re.findall(r"'([a-z_]+)'", c.execute(text(sql)).scalar_one()))

    def cols(c: Connection) -> set[str]:
        return {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'cases'"))}  # fmt: skip

    with eng.connect() as c:
        assert kinds(c) == set(KINDS)
        assert {"sla_due_at", "sla_officer_notified_for", "sla_admin_notified_for"} <= cols(c)
    command.downgrade(cfg, "0026")
    with eng.connect() as c:
        assert kinds(c) == set(KINDS) - {"case_overdue", "case_overdue_admin"}
        assert not cols(c) & {"sla_due_at", "sla_officer_notified_for", "sla_admin_notified_for"}
    eng.dispose()
