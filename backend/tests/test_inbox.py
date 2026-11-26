"""The in-app inbox (notifications, Part 1): every trigger writes exactly one row for the right
person and none for anyone else; a person reads only their own rows; the auditor gets nothing and
403 on every route; no row carries a name, a number, a score or an outcome; and a notification
stands or falls with the event it belongs to (one transaction)."""

import json
import re
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.api.security import hash_password
from app.db.migrate import alembic_config
from app.notifications import inbox
from app.notifications.check import check_notification_text
from app.notifications.inbox import KINDS, NotificationContentError, notify
from tests import test_auditor
from tests.rag_helpers import fake_embed_passages
from tests.test_admin_cases import REASON, decide, override
from tests.test_api import (
    PASSWORD,
    add_precedent,
    application,
    create,
    first_clean_dev_case,
    login,
    minimal,
    needs_cases,
    upload_all,
    wait_for,
)
from tests.test_auditor import seed_case
from tests.test_learning import run_override
from tests.test_notifications import Flaky, done_case, draft
from tests.test_upload_links import MORE, REQUEST, make_link, pfiles, tok

pytestmark = pytest.mark.db
client = test_auditor.client  # the same app, database and users as the auditor tests
engine = test_auditor.engine
V1 = "/api/v1"
OUTCOME_WORDS = re.compile(
    r"approv|reject|declin|recommend|refer|eligible|sanction|score|band|\brule|foir|cibil|point",
    re.I,
)


# --------------------------------------------------------------------------- helpers
def rows(engine: Engine, who: str | None = None, kind: str | None = None) -> list[Any]:
    """Notification rows, optionally for one person (by first name) and one kind."""
    with engine.connect() as c:
        return list(c.execute(
            text("""SELECT n.*, u.email FROM notifications n JOIN users u ON u.id = n.user_id
                    WHERE (CAST(:w AS text) IS NULL OR u.email = :w || '@example.test')
                      AND (CAST(:k AS text) IS NULL OR n.kind = :k) ORDER BY n.created_at, n.id"""),
            {"w": who, "k": kind},
        ))  # fmt: skip


def who_got(engine: Engine, kind: str) -> list[str]:
    return sorted(r.email.split("@")[0] for r in rows(engine, kind=kind))


def add_user(engine: Engine, name: str, role: str, *, active: bool = True) -> None:
    with engine.begin() as c:
        c.execute(
            text("""INSERT INTO users (name, email, password_hash, role, active)
                    VALUES (:n, :e, :h, :r, :a)"""),
            {"n": name, "e": f"{name.split()[0].lower()}@example.test",
             "h": hash_password(PASSWORD), "r": role, "a": active},
        )  # fmt: skip


def user_id(engine: Engine, who: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("SELECT id FROM users WHERE email = :e"),
                             {"e": f"{who}@example.test"}).scalar_one())  # fmt: skip


def applicant_sends(client: TestClient, h: dict[str, str]) -> tuple[dict[str, str], str]:
    """The applicant opens a link, sends the request and a file, presses Send. Returns the token
    header and the reference."""
    token = make_link(client, h)["token"]
    assert client.post(f"{V1}/public/request", json=REQUEST, headers=tok(token)).status_code == 200
    client.post(f"{V1}/public/files", files=pfiles("p.pdf"), headers=tok(token))
    sent = client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(token))
    assert sent.status_code == 200
    return tok(token), sent.json()["reference"]


# --------------------------------------------------------------------------- the table of kinds
def test_every_text_in_the_table_is_clean_and_holds_no_number_or_outcome_word() -> None:
    assert len(KINDS) == 15  # 13 + the two overdue reminders (Stage 12 Part C)
    for kind in KINDS.values():
        titles = [kind.title, *(t for _, t in kind.variants)]
        for t in titles:
            blob = f"{t}\n{kind.body}"
            assert check_notification_text(blob) == [], kind.key
            assert not re.search(r"\d", blob), kind.key  # no number at all
            assert not OUTCOME_WORDS.search(blob), (kind.key, blob)
            assert len(t) <= 80 and len(kind.body) <= 80
        assert set(kind.roles) <= {"officer", "admin"}  # never the auditor


def test_every_kind_is_in_exactly_one_filter_group_and_each_role_sees_its_own_groups() -> None:
    in_groups = [k for _, _, kinds in inbox.GROUPS for k in kinds]
    assert sorted(in_groups) == sorted(KINDS)  # none missing, none twice
    officer = [g["key"] for g in inbox.groups_for("officer")]
    admin = [g["key"] for g in inbox.groups_for("admin")]
    assert officer == ["applicant", "runs", "decisions", "precedents", "messages"]
    assert admin == ["decisions", "precedents", "messages"] and inbox.groups_for("auditor") == []
    assert (
        inbox.kinds_in("runs") == ["run_ready", "run_stopped_fix"] and inbox.kinds_in("x") is None
    )


def test_the_kinds_in_code_are_exactly_the_kinds_the_database_accepts(engine: Engine) -> None:
    with engine.connect() as c:
        allowed = c.execute(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                 "WHERE conname = 'notifications_kind_check'")).scalar_one()  # fmt: skip
    assert set(re.findall(r"'([a-z_]+)'", allowed)) == set(KINDS)


def test_a_bad_text_fails_loudly_in_dev_and_is_dropped_and_logged_in_production(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    uid = user_id(engine, "asha")
    bad = inbox.Kind("run_ready", ("officer",), "x", "x", "Your score is 72 out of 100", "", "case")
    monkeypatch.setitem(KINDS, "run_ready", bad)
    with engine.begin() as c, pytest.raises(NotificationContentError):
        notify(c, uid, "run_ready")
    try:
        inbox.configure(strict=False)
        with caplog.at_level("ERROR", logger="loan_copilot.notifications"), engine.begin() as c:
            assert notify(c, uid, "run_ready") is None
        assert "dropped by the content check" in caplog.text
    finally:
        inbox.configure(strict=True)
    assert rows(engine) == []


def test_a_notification_is_written_in_the_transaction_of_its_event(engine: Engine) -> None:
    uid = user_id(engine, "asha")
    with engine.connect() as c, c.begin() as tx:
        assert notify(c, uid, "run_ready") is not None
        tx.rollback()  # the event did not happen, so neither does the notification
    assert rows(engine) == []


def test_the_auditor_is_never_a_recipient(engine: Engine) -> None:
    with engine.begin() as c:
        assert notify(c, user_id(engine, "aud"), "run_ready") is None
        assert notify(c, user_id(engine, "asha"), "issue_filed") is None  # an admin kind
    assert rows(engine) == []


# --------------------------------------------------------------------------- the applicant
def test_applicant_request_and_send_tell_the_case_owner_once_each(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha = login(client, "asha")
    token = make_link(client, asha)["token"]
    client.post(f"{V1}/public/request", json=REQUEST, headers=tok(token))
    cid = client.get(f"{V1}/cases", headers=asha).json()[0]["id"]
    case_no = client.get(f"{V1}/cases/{cid}", headers=asha).json()["case_no"]
    (got,) = rows(engine, kind="applicant_request_received")
    assert got.email == "asha@example.test" and str(got.case_id) == cid and got.case_ref == case_no
    # an edited request, a file, and a removed file are not events the officer is told about
    client.post(f"{V1}/public/request", json={**REQUEST, "loan_amount": 300000}, headers=tok(token))
    client.post(f"{V1}/public/files", files=pfiles("p.pdf"), headers=tok(token))
    assert len(rows(engine)) == 1
    sent = client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(token))
    assert sent.status_code == 200
    (first,) = rows(engine, kind="applicant_sent")
    assert first.title == "The applicant sent their files" and str(first.case_id) == cid
    # Send pressed again (a refresh, a second tab) is not a new event
    client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(token))
    assert len(rows(engine, kind="applicant_sent")) == 1
    # the officer asks for more and the applicant sends again: a second row with its own title
    asked = client.post(f"{V1}/cases/{cid}/ask-applicant", json=MORE, headers=asha)
    assert asked.status_code == 200
    assert len(rows(engine, kind="applicant_sent")) == 1  # asking is the officer's own act
    client.post(f"{V1}/public/files", files=pfiles("more.pdf"), headers=tok(token))
    client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(token))
    again = rows(engine, kind="applicant_sent")
    assert [r.title for r in again] == ["The applicant sent their files",
                                        "The applicant sent more files"]  # fmt: skip
    assert {r.email for r in rows(engine)} == {"asha@example.test"}  # nobody else, ever


def test_a_reassigned_case_notifies_the_owner_not_the_link_officer(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha, ada = login(client, "asha"), login(client, "ada")
    token = make_link(client, asha)["token"]
    client.post(f"{V1}/public/request", json=REQUEST, headers=tok(token))
    cid = client.get(f"{V1}/cases", headers=asha).json()[0]["id"]
    moved = client.post(f"{V1}/admin/cases/{cid}/reassign", headers=ada, json={
        "second_click": True, "reason": REASON, "officer_id": user_id(engine, "ben")})  # fmt: skip
    assert moved.status_code == 200
    client.post(f"{V1}/public/files", files=pfiles("p.pdf"), headers=tok(token))
    client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(token))
    assert who_got(engine, "applicant_sent") == ["ben"]  # `cases.created_by`, now Ben


# --------------------------------------------------------------------------- the pipeline
@needs_cases
def test_a_finished_run_tells_the_owner_it_is_ready_and_a_fix_stop_says_so(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    h = login(client, "asha")
    case = first_clean_dev_case("PL")
    cid = create(client, h, application(case))
    upload_all(client, h, cid, case)
    assert client.post(f"{V1}/cases/{cid}/submit", headers=h).status_code == 202
    wait_for(client, h, cid, {"awaiting_confirmation"})
    (ready,) = rows(engine, kind="run_ready")
    assert ready.email == "asha@example.test" and str(ready.case_id) == cid
    assert rows(engine, kind="run_stopped_fix") == []

    stop_case = "SYN-PL-D08"  # blurred photographs: a fix-type stop
    sid = create(client, h, application(stop_case))
    upload_all(client, h, sid, stop_case)
    assert client.post(f"{V1}/cases/{sid}/submit", headers=h).status_code == 202
    wait_for(client, h, sid, {"stopped"}, seconds=150)
    (stopped,) = rows(engine, kind="run_stopped_fix")
    assert stopped.email == "asha@example.test" and str(stopped.case_id) == sid
    assert len(rows(engine, kind="run_ready")) == 1  # the stop is not a "ready"
    assert {r.email for r in rows(engine)} == {"asha@example.test"}


# --------------------------------------------------------------------------- the admin's acts
def test_admin_correction_and_reassignment_tell_the_right_officer(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case_id, _ = seed_case(client, engine)  # Asha's case
    decide(engine, case_id, final="approve")
    ada, asha = login(client, "ada"), login(client, "asha")
    assert override(client, ada, case_id, second_click=False).status_code == 422
    assert override(client, ada, case_id, final_decision="approve").status_code == 422
    assert rows(engine) == []  # a refused correction tells nobody
    assert override(client, ada, case_id, final_decision="reject").status_code == 200
    (got,) = rows(engine, kind="decision_corrected")
    assert got.email == "asha@example.test" and str(got.case_id) == case_id
    assert got.case_ref is not None and "reject" not in (got.title + got.body).lower()

    open_id = create(client, asha, minimal())  # a case Asha has not decided
    body = {"second_click": True, "reason": REASON, "officer_id": user_id(engine, "ben")}
    assert client.post(f"{V1}/admin/cases/{open_id}/reassign", headers=ada,
                       json={**body, "second_click": False}).status_code == 422  # fmt: skip
    assert rows(engine, kind="case_reassigned") == []
    assert (
        client.post(f"{V1}/admin/cases/{open_id}/reassign", headers=ada, json=body).status_code
        == 200
    )
    (moved,) = rows(engine, kind="case_reassigned")
    assert moved.email == "ben@example.test" and str(moved.case_id) == open_id
    assert len(rows(engine)) == 2  # Asha is not told about the case that left her


def test_the_proposer_hears_the_precedent_answer_and_nobody_else(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    ada = login(client, "ada")
    yes, no = add_precedent(engine), add_precedent(engine)
    assert (
        client.post(f"{V1}/admin/precedents/{yes}/approve", json={}, headers=ada).status_code == 200
    )
    assert (
        client.post(f"{V1}/admin/precedents/{yes}/approve", json={}, headers=ada).status_code == 409
    )
    assert (
        client.post(
            f"{V1}/admin/precedents/{no}/reject", json={"note": "thin"}, headers=ada
        ).status_code
        == 200
    )
    (added,) = rows(engine, kind="precedent_added")
    (not_added,) = rows(engine, kind="precedent_not_added")
    assert added.email == not_added.email == "asha@example.test"
    assert added.case_id is not None and re.fullmatch(r"CASE-\d{4}-\d{4}", added.case_ref)
    assert len(rows(engine)) == 2  # the refused second approval wrote nothing


def test_a_new_precedent_reaches_every_active_admin_and_a_held_one_says_it_was_held(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:  # fmt: skip
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)
    add_user(engine, "Amy Admin", "admin")
    add_user(engine, "Dan Admin", "admin", active=False)
    run_override(engine, "SYN-PL-D03", "approve")  # passes the code check: pending
    assert who_got(engine, "precedent_pending") == ["ada", "amy"]
    assert rows(engine, kind="precedent_held") == []
    run_override(engine, "SYN-PL-D11", "approve")  # approving over a hard rule: held
    assert who_got(engine, "precedent_held") == ["ada", "amy"]
    assert len(rows(engine, kind="precedent_pending")) == 2  # unchanged
    # the officer who proposed is not told at this point, and the auditor never is; the offline
    # runs finished too, which told the pipeline's own officer account and nobody else
    others = [r for r in rows(engine) if not r.kind.startswith("precedent_")]
    assert {r.kind for r in others} == {"run_ready"} and len(others) == 2
    assert {r.email for r in others} == {"pipeline@local.invalid"}
    assert {r.email for r in rows(engine) if r.kind.startswith("precedent_")} == {
        "ada@example.test", "amy@example.test"}  # fmt: skip


def test_an_issue_report_reaches_every_active_admin_and_a_blocked_one_reaches_none(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    add_user(engine, "Amy Admin", "admin")
    add_user(engine, "Dan Admin", "admin", active=False)
    asha = login(client, "asha")
    ref = client.get(f"{V1}/cases/{create(client, asha, minimal())}", headers=asha).json()[
        "case_no"
    ]
    blocked = client.post(f"{V1}/issues", headers=asha, json={
        "category": "bug", "body": "The page froze for PAN ABCDE1234F today"})  # fmt: skip
    assert blocked.status_code == 422 and rows(engine) == []
    filed = client.post(f"{V1}/issues", headers=asha, json={
        "category": "bug", "case_ref": ref,
        "body": "The page froze when I saved the case"})  # fmt: skip
    assert filed.status_code == 201
    assert who_got(engine, "issue_filed") == ["ada", "amy"]
    assert {r.case_ref for r in rows(engine)} == {ref}
    assert all(r.case_id is None for r in rows(engine))  # the issue never joins to case data
    assert len(rows(engine)) == 2


# --------------------------------------------------------------------------- messages and links
def test_a_failed_customer_message_tells_the_sender_once(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    sender = Flaky()
    client.app.state.sender = sender  # type: ignore[attr-defined]
    case_id, h = done_case(client, engine)
    m = draft(client, h, case_id).json()
    url = f"{V1}/messages/{m['id']}/send"
    assert client.post(url, headers=h, json={"second_click": True}).status_code == 502
    (got,) = rows(engine, kind="message_failed")
    assert got.email == "asha@example.test" and str(got.case_id) == case_id
    sender.ok = True  # the retry works: the officer sees the message as sent, no new row
    assert client.post(url, headers=h, json={"second_click": True}).status_code == 200
    assert len(rows(engine, kind="message_failed")) == 1 and len(rows(engine)) == 1


def set_expiry(engine: Engine, link_id: str, hours: float) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE upload_links SET expires_at = now() + make_interval(hours => :h) "
                       "WHERE id = :i"), {"h": hours, "i": link_id})  # fmt: skip


def test_a_link_ending_within_a_day_is_announced_once_per_expiry_on_read(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha, ben = login(client, "asha"), login(client, "ben")
    far, soon = make_link(client, asha), make_link(client, asha)
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json() == {"unread": 0}
    set_expiry(engine, soon["id"], 12)
    set_expiry(engine, far["id"], 48)
    assert client.get(f"{V1}/notifications/unread-count", headers=ben).json() == {"unread": 0}
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json() == {"unread": 1}
    for _ in range(3):  # reading again, or listing, adds nothing
        assert client.get(f"{V1}/notifications/unread-count", headers=asha).json()["unread"] == 1
        assert client.get(f"{V1}/notifications", headers=asha).json()["total"] == 1
    (item,) = client.get(f"{V1}/notifications", headers=asha).json()["items"]
    assert item["kind"] == "link_expiring" and item["path"] == "/links" and item["case_id"] is None
    # extended, then ending within a day again: announced again for the new expiry
    set_expiry(engine, soon["id"], 20)
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json()["unread"] == 2
    # switched off: nothing to announce
    client.post(f"{V1}/links/{far['id']}/disable", json={"second_click": True}, headers=asha)
    set_expiry(engine, far["id"], 3)
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json()["unread"] == 2


def test_an_expiring_link_with_a_waiting_applicant_points_at_its_case_and_a_sent_one_is_quiet(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha = login(client, "asha")
    waiting = make_link(client, asha)
    client.post(f"{V1}/public/request", json=REQUEST, headers=tok(waiting["token"]))
    cid = client.get(f"{V1}/cases", headers=asha).json()[0]["id"]
    done = make_link(client, asha)  # a second case, sent by the applicant
    client.post(f"{V1}/public/request", json=REQUEST, headers=tok(done["token"]))
    client.post(f"{V1}/public/files", files=pfiles("p.pdf"), headers=tok(done["token"]))
    client.post(f"{V1}/public/send", json={"second_click": True}, headers=tok(done["token"]))
    base = len(rows(engine))
    set_expiry(engine, waiting["id"], 5)
    set_expiry(engine, done["id"], 5)
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json()["unread"] == base + 1
    (got,) = rows(engine, kind="link_expiring")
    assert str(got.case_id) == cid and got.case_ref is not None
    items = client.get(f"{V1}/notifications", headers=asha).json()["items"]
    assert items[0]["path"] == f"/links?case={cid}"


# --------------------------------------------------------------------------- who reads what
def seed_three(engine: Engine) -> None:
    with engine.begin() as c:
        notify(c, user_id(engine, "asha"), "run_ready")
        notify(c, user_id(engine, "asha"), "case_reassigned")
        notify(c, user_id(engine, "asha"), "message_failed")
        notify(c, user_id(engine, "ben"), "run_ready")
        notify(c, user_id(engine, "ada"), "precedent_pending")


def test_a_person_reads_and_marks_only_their_own_rows(client: TestClient, engine: Engine) -> None:
    seed_three(engine)
    asha, ben, ada = login(client, "asha"), login(client, "ben"), login(client, "ada")
    mine = client.get(f"{V1}/notifications", headers=asha).json()
    assert mine["total"] == 3 and mine["unread"] == 3
    assert {i["kind"] for i in mine["items"]} == {"run_ready", "case_reassigned", "message_failed"}
    theirs = mine["items"][0]["id"]
    # another officer, and the admin, get 404 (not 403) for a row that is not theirs
    for who in (ben, ada):
        assert client.post(f"{V1}/notifications/{theirs}/read", headers=who).status_code == 404
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json() == {"unread": 3}
    assert client.post(f"{V1}/notifications/{theirs}/read", headers=asha).status_code == 200
    assert client.get(f"{V1}/notifications/unread-count", headers=asha).json() == {"unread": 2}
    assert client.get(f"{V1}/notifications/unread-count", headers=ben).json() == {"unread": 1}
    assert client.get(f"{V1}/notifications", headers=ada).json()["total"] == 1
    # an unknown id is the same 404
    assert client.post(f"{V1}/notifications/{'0' * 8}-0000-4000-8000-{'0' * 12}/read",
                       headers=asha).status_code == 404  # fmt: skip


def test_mark_read_is_idempotent_read_all_touches_only_the_callers_rows(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    seed_three(engine)
    asha, ben = login(client, "asha"), login(client, "ben")
    first = client.get(f"{V1}/notifications", headers=asha).json()["items"][0]["id"]
    a = client.post(f"{V1}/notifications/{first}/read", headers=asha).json()
    b = client.post(f"{V1}/notifications/{first}/read", headers=asha).json()
    assert a["read_at"] is not None and a["read_at"] == b["read_at"]  # the first time is kept
    done = client.post(f"{V1}/notifications/read-all", headers=asha).json()
    assert done == {"marked": 2, "unread": 0}  # the third was already read
    assert client.post(f"{V1}/notifications/read-all", headers=asha).json()["marked"] == 0
    assert client.get(f"{V1}/notifications/unread-count", headers=ben).json() == {"unread": 1}
    assert client.get(f"{V1}/notifications?unread=true", headers=asha).json()["items"] == []
    assert client.get(f"{V1}/notifications", headers=asha).json()["total"] == 3  # nothing deleted


def test_the_list_filters_unread_and_pages(client: TestClient, engine: Engine) -> None:
    uid = user_id(engine, "asha")
    with engine.begin() as c:
        for _ in range(5):
            notify(c, uid, "run_ready")
    asha = login(client, "asha")
    page = client.get(f"{V1}/notifications?limit=2&offset=2", headers=asha).json()
    assert len(page["items"]) == 2 and page["total"] == 5 and page["limit"] == 2
    ids = [
        i["id"] for i in client.get(f"{V1}/notifications?limit=100", headers=asha).json()["items"]
    ]
    assert [i["id"] for i in page["items"]] == ids[2:4]  # newest first, stable
    client.post(f"{V1}/notifications/{ids[0]}/read", headers=asha)
    unread = client.get(f"{V1}/notifications?unread=true", headers=asha).json()
    assert unread["total"] == 4 and ids[0] not in [i["id"] for i in unread["items"]]
    assert client.get(f"{V1}/notifications?limit=0", headers=asha).status_code == 422
    assert client.get(f"{V1}/notifications?limit=101", headers=asha).status_code == 422
    assert client.get(f"{V1}/notifications?offset=-1", headers=asha).status_code == 422


def test_the_list_filters_by_group_and_case_number_on_the_callers_own_rows(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    uid, ben_id = user_id(engine, "asha"), user_id(engine, "ben")
    with engine.begin() as c:
        one = c.execute(text("INSERT INTO cases (case_no, loan_type, created_by, loan_amount, "
            "tenure_months) VALUES ('CASE-2026-0101', 'personal', :u, 1000, 12) RETURNING id"),
            {"u": uid}).scalar_one()  # fmt: skip
        two = c.execute(text("INSERT INTO cases (case_no, loan_type, created_by, loan_amount, "
            "tenure_months) VALUES ('CASE-2026-0202', 'personal', :u, 1000, 12) RETURNING id"),
            {"u": uid}).scalar_one()  # fmt: skip
        notify(c, uid, "run_ready", inbox.CaseRef(one, "CASE-2026-0101"))
        notify(c, uid, "run_stopped_fix", inbox.CaseRef(two, "CASE-2026-0202"))
        notify(c, uid, "applicant_sent", inbox.CaseRef(two, "CASE-2026-0202"))
        notify(c, uid, "message_failed")  # no case at all
        notify(c, ben_id, "run_ready", inbox.CaseRef(None, "CASE-2026-0101"))  # someone else's
    asha = login(client, "asha")

    def ask(query: str) -> dict[str, Any]:
        r = client.get(f"{V1}/notifications?{query}", headers=asha)
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]

    assert ask("")["total"] == 4
    assert {i["kind"] for i in ask("group=runs")["items"]} == {"run_ready", "run_stopped_fix"}
    assert [i["kind"] for i in ask("group=messages")["items"]] == ["message_failed"]
    assert ask("case=0202")["total"] == 2  # a part of the number is enough, any case
    assert ask("case=case-2026-0101")["total"] == 1  # and it ignores capitals
    assert ask("group=runs&case=0202")["total"] == 1  # filters combine
    assert ask("case=0909")["total"] == 0
    # a filter never lets one person see another's rows (Ben's notice is for the same case)
    assert ask("case=0101")["total"] == 1
    # what filters are offered depends on the role; the counts beside it do not change
    assert [g["key"] for g in ask("")["groups"]][0] == "applicant" and ask("group=runs")[
        "unread"
    ] == 4
    assert client.get(f"{V1}/notifications?group=nope", headers=asha).status_code == 422
    for bad in ("a%25", "x y", "A" * 15):
        assert client.get(f"{V1}/notifications?case={bad}", headers=asha).status_code == 422
    ada = login(client, "ada")
    assert [g["key"] for g in client.get(f"{V1}/notifications", headers=ada).json()["groups"]] == [
        "decisions", "precedents", "messages"]  # fmt: skip


def test_the_auditor_gets_403_on_every_route_and_has_no_rows(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    seed_three(engine)
    aud = login(client, "aud")
    some = user_id(engine, "asha")
    with engine.connect() as c:
        nid = c.execute(text("SELECT id FROM notifications WHERE user_id = :u LIMIT 1"),
                        {"u": some}).scalar_one()  # fmt: skip
    for method, path in (("GET", "/notifications"), ("GET", "/notifications/unread-count"),
                         ("POST", "/notifications/read-all"),
                         ("POST", f"/notifications/{nid}/read")):  # fmt: skip
        assert client.request(method, V1 + path, headers=aud).status_code == 403, path
    assert client.get(f"{V1}/notifications").status_code == 401  # signed out
    assert rows(engine, "aud") == []


# --------------------------------------------------------------------------- no personal data
def test_no_notification_holds_a_name_a_number_a_score_or_an_outcome(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    """A case for a known synthetic person, taken through every event that does not need the
    slow pipeline; then every row is searched for the person, their numbers and outcome words."""
    case_id, _ = seed_case(client, engine)  # the applicant is "Test Person"
    asha, ada = login(client, "asha"), login(client, "ada")
    decide(engine, case_id, final="approve")
    assert override(client, ada, case_id, final_decision="reject").status_code == 200
    open_id = create(client, asha, minimal())
    client.post(f"{V1}/admin/cases/{open_id}/reassign", headers=ada, json={
        "second_click": True, "reason": REASON, "officer_id": user_id(engine, "ben")})  # fmt: skip
    applicant_sends(client, asha)
    own_ref = client.get(f"{V1}/cases/{case_id}", headers=asha).json()["case_no"]
    client.post(f"{V1}/issues", headers=asha, json={
        "category": "wrong_result", "case_ref": own_ref,
        "body": "The page froze when I saved the case"})  # fmt: skip
    pid = add_precedent(engine)
    client.post(f"{V1}/admin/precedents/{pid}/approve", json={}, headers=ada)
    everything = rows(engine)
    assert {r.kind for r in everything} >= {"decision_corrected", "case_reassigned",
        "applicant_request_received", "applicant_sent", "issue_filed", "precedent_added"}  # fmt: skip
    for r in everything:
        shown = f"{r.title}\n{r.body}"
        assert not re.search(r"\btest\b|\bperson\b|asha|ben|ada", shown, re.I), shown
        assert not re.search(r"ABCDE|9876543210|1234|example", shown, re.I), shown
        assert not re.search(r"\d", shown) and not OUTCOME_WORDS.search(shown), shown
        assert r.case_ref is None or re.fullmatch(r"CASE-\d{4}-\d{4}", r.case_ref)
    # and none of it reaches the API's JSON in another shape
    for who in (asha, ada):
        blob = json.dumps(client.get(f"{V1}/notifications?limit=100", headers=who).json())
        assert not re.search(r"Test Person|ABCDE1234F|9876543210|test\.person", blob)


# --------------------------------------------------------------------------- the migration
def test_the_notifications_migration_applies_rolls_back_and_applies_again(
    clean_db_url: str,
) -> None:  # fmt: skip
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "head")
    eng = create_engine(clean_db_url)

    def shape() -> tuple[int, int]:
        with eng.connect() as c:
            table = c.execute(
                text("SELECT count(*) FROM pg_tables WHERE tablename = 'notifications'")
            )
            column = c.execute(text("SELECT count(*) FROM information_schema.columns "
                                    "WHERE table_name = 'upload_links' "
                                    "AND column_name = 'expiry_notified_for'"))  # fmt: skip
            return int(table.scalar_one()), int(column.scalar_one())

    assert shape() == (1, 1)
    command.downgrade(cfg, "0018")
    assert shape() == (0, 0)
    command.upgrade(cfg, "head")
    assert shape() == (1, 1)
    eng.dispose()
