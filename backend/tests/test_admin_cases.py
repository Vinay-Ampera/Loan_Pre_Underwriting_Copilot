"""The admin's part in a case: read every case (documents too), correct a decision the officer has
already made (reason, second click, never over a hard rule), hand an undecided case to another
officer, read sent messages and the audit log. The officer's own decision is never edited."""

import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests import test_auditor
from tests.test_api import create, login, minimal
from tests.test_auditor import seed_case

pytestmark = pytest.mark.db
client = test_auditor.client  # the same app, database and users as the auditor tests
engine = test_auditor.engine
V1 = "/api/v1"
REASON = "The branch manager reviewed the file and disagrees."


def decide(engine: Engine, case_id: str, *, action: str = "confirm", final: str = "approve",
           findings: list[dict[str, str]] | None = None, status: str | None = None) -> None:  # fmt: skip
    """Make the case look decided by Asha, with a report that carries the given findings."""
    with engine.begin() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = 'asha@example.test'")).scalar_one()
        c.execute(text("UPDATE reports SET report_json = CAST(:r AS jsonb) WHERE case_id = :c"),
                  {"c": case_id, "r": json.dumps({"findings": findings or [], "summary": "x"})})  # fmt: skip
        c.execute(
            text("""INSERT INTO officer_actions (case_id, officer_id, action, original_recommendation,
                        final_decision, reason, second_click_at)
                    VALUES (:c, :u, :a, 'recommend_approve', :f, 'because it is fine', now())"""),
            {"c": case_id, "u": uid, "a": action, "f": final},
        )
        c.execute(text("UPDATE cases SET status = :s WHERE id = :c"),
                  {"c": case_id, "s": status or ("confirmed" if action == "confirm" else "overridden")})  # fmt: skip


def override(client: TestClient, who: dict[str, str], case_id: str, **body: object) -> object:
    payload = {"second_click": True, "reason": REASON, "final_decision": "reject", **body}
    return client.post(f"{V1}/admin/cases/{case_id}/override", headers=who, json=payload)


# --------------------------------------------------------------------------- reading
def test_admin_reads_every_case_and_its_documents_but_the_auditor_cannot(
    client: TestClient, engine: Engine, tmp_path: Path
) -> None:
    case_id, _ = seed_case(client, engine)
    create(client, login(client, "ben"), minimal())
    ada, aud = login(client, "ada"), login(client, "aud")
    rows = client.get(f"{V1}/cases", headers=ada).json()
    assert len(rows) == 2 and {r["officer"] for r in rows} == {"Asha Officer", "Ben Officer"}
    body = client.get(f"{V1}/cases/{case_id}", headers=ada).json()
    a = body["applicants"][0]
    assert a["full_name"] == "Test Person" and a["pan"] == "ABCDE****F"  # names shown, ids masked
    assert body["officer"] == "Asha Officer" and body["admin_block"] is not None
    assert client.get(f"{V1}/cases/{case_id}/report", headers=ada).status_code == 200
    assert client.get(f"{V1}/cases/{case_id}/audit", headers=ada).status_code == 200
    assert client.get(f"{V1}/cases/{case_id}", headers=aud).status_code == 403
    with engine.connect() as c:
        doc = c.execute(text("SELECT id FROM documents")).scalar_one()
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.4")
    with engine.begin() as c:
        c.execute(
            text("UPDATE documents SET file_path = :p WHERE id = :d"), {"p": str(f), "d": doc}
        )
    assert client.get(f"{V1}/cases/{case_id}/documents/{doc}/file", headers=ada).status_code == 200
    assert client.get(f"{V1}/cases/{case_id}/documents/{doc}/file", headers=aud).status_code == 403


def test_the_admin_still_cannot_act_as_an_officer(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    ada = login(client, "ada")
    for tail in ("confirm", "override", "submit", "resume", "documents"):
        assert client.post(f"{V1}/cases/{case_id}/{tail}", headers=ada, json={}).status_code == 403
    assert client.post(f"{V1}/cases/{case_id}/messages", headers=ada, json={}).status_code == 403


# --------------------------------------------------------------------------- override
def test_admin_override_is_a_separate_record_and_the_latest_one_is_in_force(
    client: TestClient, engine: Engine
) -> None:
    case_id, _ = seed_case(client, engine)
    decide(engine, case_id, final="approve")
    ada, asha = login(client, "ada"), login(client, "asha")
    assert override(client, ada, case_id, final_decision="reject").status_code == 200
    assert override(client, ada, case_id, final_decision="refer").status_code == 200  # again, fine

    body = client.get(f"{V1}/cases/{case_id}", headers=asha).json()  # the officer sees it too
    assert body["decision_in_force"] == "refer"
    assert body["officer_action"]["final_decision"] == "approve"  # the officer's row is untouched
    chain = body["admin_actions"]
    assert [(a["previous_decision"], a["final_decision"]) for a in chain] == [
        ("approve", "reject"), ("reject", "refer")]  # fmt: skip
    assert chain[0]["admin"] == "Ada Admin" and chain[0]["reason"] == REASON
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM officer_actions")).scalar_one() == 1
        log = c.execute(
            text("SELECT before, after FROM audit_log WHERE action = 'admin_override'")
        ).all()
    assert (
        len(log) == 2
        and log[0].after == {"final": "reject"}
        and log[0].before == {"decision": "approve"}
    )


def test_admin_override_checks(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    ada, asha, aud = login(client, "ada"), login(client, "asha"), login(client, "aud")
    # not decided by the officer yet
    assert override(client, ada, case_id).status_code == 409
    decide(engine, case_id, final="approve")
    assert override(client, ada, case_id, second_click=False).status_code == 422
    assert override(client, ada, case_id, reason="too short").status_code == 422
    assert override(client, ada, case_id, final_decision="approve").status_code == 422  # same
    assert override(client, asha, case_id).status_code == 403
    assert override(client, aud, case_id).status_code == 403
    assert override(client, ada, str(uuid.uuid4())).status_code == 404
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM admin_actions")).scalar_one() == 0


def test_a_hard_rule_cannot_be_overridden_by_an_admin(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    decide(engine, case_id, action="override", final="approve",
           findings=[{"rule_id": "CM-AGE-01", "severity": "hard_fail"}])  # fmt: skip
    ada = login(client, "ada")
    r = override(client, ada, case_id, final_decision="reject")
    assert r.status_code == 409 and "hard rule" in r.json()["detail"]  # type: ignore[attr-defined]
    assert "hard rule" in client.get(f"{V1}/cases/{case_id}", headers=ada).json()["admin_block"]
    # a cap to refer is a hard rule too; a points-lost finding is not
    with engine.begin() as c:
        c.execute(text("""UPDATE reports SET report_json = '{"findings": [{"severity": "points_lost"}]}'
                          WHERE case_id = :c"""), {"c": case_id})  # fmt: skip
    assert override(client, ada, case_id, final_decision="reject").status_code == 200
    assert client.get(f"{V1}/cases/{case_id}", headers=ada).json()["admin_block"] is None


# --------------------------------------------------------------------------- reassign
def reassign(
    client: TestClient, who: dict[str, str], case_id: str, officer_id: str, **body: object
) -> object:
    payload = {"second_click": True, "reason": REASON, "officer_id": officer_id, **body}
    return client.post(f"{V1}/admin/cases/{case_id}/reassign", headers=who, json=payload)


def user_id(engine: Engine, name: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("SELECT id FROM users WHERE email = :e"),
                             {"e": f"{name}@example.test"}).scalar_one())  # fmt: skip


def test_admin_reassigns_an_undecided_case_and_the_new_officer_owns_it(
    client: TestClient, engine: Engine
) -> None:
    case_id, _ = seed_case(client, engine)
    ada, asha, ben = login(client, "ada"), login(client, "asha"), login(client, "ben")
    ben_id = user_id(engine, "ben")
    assert reassign(client, ada, case_id, ben_id).status_code == 200  # type: ignore[attr-defined]
    assert client.get(f"{V1}/cases/{case_id}", headers=asha).status_code == 404
    assert client.get(f"{V1}/cases/{case_id}", headers=ben).status_code == 200
    with engine.connect() as c:
        row = c.execute(
            text("SELECT before, after FROM audit_log WHERE action = 'case_reassigned'")
        ).one()
    assert row.before == {"officer": "Asha Officer"} and row.after["officer"] == "Ben Officer"


def test_reassign_refuses_decided_running_or_bad_targets(
    client: TestClient, engine: Engine
) -> None:
    case_id, _ = seed_case(client, engine)
    ada, asha = login(client, "ada"), login(client, "asha")
    ben_id, asha_id, ada_id = (
        user_id(engine, "ben"),
        user_id(engine, "asha"),
        user_id(engine, "ada"),
    )
    assert reassign(client, ada, case_id, asha_id).status_code == 422  # already theirs
    assert reassign(client, ada, case_id, ada_id).status_code == 422  # not an officer
    assert reassign(client, ada, case_id, str(uuid.uuid4())).status_code == 422
    assert reassign(client, ada, case_id, ben_id, second_click=False).status_code == 422
    assert reassign(client, ada, case_id, ben_id, reason="short").status_code == 422
    assert reassign(client, asha, case_id, ben_id).status_code == 403
    with engine.begin() as c:
        c.execute(text("UPDATE users SET active = false WHERE email = 'ben@example.test'"))
    assert reassign(client, ada, case_id, ben_id).status_code == 422  # disabled officer
    with engine.begin() as c:
        c.execute(text("UPDATE users SET active = true WHERE email = 'ben@example.test'"))
        c.execute(text("UPDATE cases SET status = 'running' WHERE id = :c"), {"c": case_id})
    assert reassign(client, ada, case_id, ben_id).status_code == 409
    decide(engine, case_id)
    assert reassign(client, ada, case_id, ben_id).status_code == 409  # decided: only an override
    assert reassign(client, ada, str(uuid.uuid4()), ben_id).status_code == 404


def test_users_list_counts_each_officers_open_cases(client: TestClient, engine: Engine) -> None:
    seed_case(client, engine)
    ada = login(client, "ada")
    users = {u["email"]: u for u in client.get(f"{V1}/admin/users", headers=ada).json()}
    assert (
        users["asha@example.test"]["open_cases"] == 1
        and users["ben@example.test"]["open_cases"] == 0
    )
    asha = user_id(engine, "asha")
    got = client.get(f"{V1}/admin/users/{asha}/activity", headers=ada).json()
    assert got["cases_total"] == 1 and got["cases"][0]["applicant"] == "Test Person"
    assert got["cases"][0]["corrected"] is False and "id" in got["cases"][0]


# --------------------------------------------------------------------------- lists
def test_recent_decisions_flags_corrected_cases(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    ada = login(client, "ada")
    assert client.get(f"{V1}/admin/recent-decisions", headers=ada).json() == []
    decide(engine, case_id)
    rows = client.get(f"{V1}/admin/recent-decisions", headers=ada).json()
    assert len(rows) == 1 and rows[0]["corrected"] is False and rows[0]["officer"] == "Asha Officer"
    override(client, ada, case_id)
    assert client.get(f"{V1}/admin/recent-decisions", headers=ada).json()[0]["corrected"] is True
    assert (
        client.get(f"{V1}/admin/recent-decisions", headers=login(client, "asha")).status_code == 403
    )


def test_admin_sees_sent_messages_only(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)  # one sent message
    with engine.begin() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = 'asha@example.test'")).scalar_one()
        for status in ("draft", "blocked", "failed"):
            c.execute(text("""INSERT INTO outbox (case_id, sent_by, recipient_email, template, subject, body,
                                  status) VALUES (:c, :u, 'x@example.com', 'blank', 'Hi', 'Call me.', :s)"""),
                      {"c": case_id, "u": uid, "s": status})  # fmt: skip
    ada = login(client, "ada")
    rows = client.get(f"{V1}/admin/messages", headers=ada).json()
    assert len(rows) == 1 and rows[0]["officer"] == "Asha Officer" and "OTP" in rows[0]["text"]
    assert rows[0]["recipient"] == "****@example.com" and rows[0]["template_label"]
    for who in ("asha", "aud"):
        assert client.get(f"{V1}/admin/messages", headers=login(client, who)).status_code == 403


def test_admin_audit_log_is_unmasked_with_case_ids_and_filters(
    client: TestClient, engine: Engine
) -> None:
    case_id, _ = seed_case(client, engine)
    ada = login(client, "ada")
    decide(engine, case_id)
    override(client, ada, case_id)
    log = client.get(
        f"{V1}/admin/audit-log", params={"action": "admin_override"}, headers=ada
    ).json()
    assert log["total"] == 1 and log["rows"][0]["case_id"] == case_id
    assert log["rows"][0]["actor"] == "Ada Admin" and log["rows"][0]["actor_role"] == "admin"
    me = client.get(f"{V1}/auth/me", headers=ada).json()
    mine = client.get(f"{V1}/admin/audit-log", params={"actor": me["id"]}, headers=ada).json()
    assert mine["total"] >= 2  # the login and the override
    today = date.today().isoformat()
    assert (
        client.get(f"{V1}/admin/audit-log", params={"date_from": today}, headers=ada).json()[
            "total"
        ]
        >= 2
    )
    assert (
        client.get(f"{V1}/admin/audit-log", params={"date_from": "2999-01-01"}, headers=ada).json()[
            "total"
        ]
        == 0
    )
    csv_ = client.get(f"{V1}/admin/audit-log.csv", params={"action": "admin_override"}, headers=ada)
    assert "admin override" not in csv_.text and "admin_override" in csv_.text
    assert "admin_override" in client.get(f"{V1}/admin/audit-log/actions", headers=ada).json()
    for who in ("asha", "aud"):
        assert client.get(f"{V1}/admin/audit-log", headers=login(client, who)).status_code == 403


def test_the_decision_chain_reaches_the_officer_report(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    decide(engine, case_id)
    override(client, login(client, "ada"), case_id)
    rep = client.get(f"{V1}/cases/{case_id}/report", headers=login(client, "asha")).json()
    assert rep["admin_actions"][0]["final_decision"] == "reject"
