"""The applicant upload link (Stage 10, Part C) over HTTP: who may create, extend and disable a
link; that the token is shown once and kept only as a hash; that unknown, expired and disabled
tokens all get the same answer; that the public page reads back nothing but checklist counts;
the officer's inbox and the request lock; neutral refusal once the case is running; rate limits;
and the upload-link message. The sender is a stand-in; the database is a throwaway one."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.links import hash_token
from app.api.ratelimit import RateLimiter
from app.api.security import hash_password
from app.notifications.sender import Outgoing
from tests.test_api import (
    PASSWORD,
    audit_rows,
    client,  # noqa: F401 - fixture
    engine,  # noqa: F401 - fixture
    first_clean_dev_case,
    login,
    needs_cases,
)
from tests.test_intake_desk import as_files, case_files, desk_form, push, say_employment, start

pytestmark = pytest.mark.db
FIX = Path(__file__).parent / "fixtures"
PAYSLIP = (FIX / "payslip_clean.pdf").read_bytes()
REQUEST = {"loan_type": "personal", "loan_amount": 250000, "tenure_months": 24,
           "purpose": "Home repairs", "employment_type": "salaried",
           "declared_monthly_income": 60000}  # fmt: skip


def make_link(client: TestClient, h: dict[str, str], **over: Any) -> dict[str, Any]:
    r = client.post("/api/v1/links", json={"second_click": True, **over}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def tok(token: str) -> dict[str, str]:
    return {"X-Upload-Token": token}


def pfiles(*names: str) -> list[Any]:
    return [("files", (n, PAYSLIP, "application/pdf")) for n in names]


# --------------------------------------------------------------------------- creating and keeping
def test_a_link_needs_the_second_click_and_the_token_is_shown_once_and_kept_as_a_hash(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    h = login(client, "asha")
    assert client.post("/api/v1/links", json={}, headers=h).status_code == 422
    assert client.post("/api/v1/links", json={"second_click": False}, headers=h).status_code == 422
    made = make_link(client, h)
    token = made["token"]
    assert len(token) >= 32 and made["path"] == f"/u#{token}" and made["shown_once"]
    listing = client.get("/api/v1/links", headers=h).json()
    assert [x["id"] for x in listing] == [made["id"]] and token not in json.dumps(listing)
    with engine.connect() as c:
        stored = c.execute(text("SELECT token_hash FROM upload_links")).scalar_one()
        everything = json.dumps(
            [dict(r._mapping) for r in c.execute(text("SELECT * FROM audit_log"))], default=str
        )
    assert stored == hash_token(token) and token not in stored
    assert token not in everything and made["id"] in everything  # the audit row carries the id
    assert len(audit_rows(engine, "upload_link_created")) == 1


def test_who_may_manage_links(client: TestClient, engine: Engine) -> None:
    asha, ben, ada = login(client, "asha"), login(client, "ben"), login(client, "ada")
    mine = make_link(client, asha)
    # an admin must name an officer; an officer cannot name another
    assert client.post("/api/v1/links", json={"second_click": True}, headers=ada).status_code == 422
    ben_id = next(
        u["id"]
        for u in client.get("/api/v1/admin/users", headers=ada).json()
        if u["email"] == "ben@example.test"
    )
    by_admin = make_link(client, ada, officer_id=ben_id)
    assert [x["id"] for x in client.get("/api/v1/links", headers=ben).json()] == [by_admin["id"]]
    assert {x["id"] for x in client.get("/api/v1/links", headers=ada).json()} == {
        mine["id"],
        by_admin["id"],
    }
    # nobody else's link can be disabled, extended or even seen
    assert (
        client.post(
            f"/api/v1/links/{mine['id']}/disable", json={"second_click": True}, headers=ben
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/links/{mine['id']}/extend", json={}, headers=ben).status_code == 404
    )
    assert client.get("/api/v1/links").status_code == 401
    with engine.begin() as c:  # the auditor has no link access at all
        c.execute(text("INSERT INTO users (name, email, password_hash, role) VALUES ('Audi', 'audi@example.test', :h, 'auditor')"),
                  {"h": hash_password(PASSWORD)})  # fmt: skip
    audi = login(client, "audi")
    assert client.get("/api/v1/links", headers=audi).status_code == 403
    assert (
        client.post("/api/v1/links", json={"second_click": True}, headers=audi).status_code == 403
    )
    assert client.get("/api/v1/public/link").status_code == 404  # no token: the generic answer


def test_disable_needs_the_second_click_and_extend_does_not(
    client: TestClient, engine: Engine
) -> None:
    h = login(client, "asha")
    made = make_link(client, h, days=1)
    assert client.get("/api/v1/public/link", headers=tok(made["token"])).status_code == 200
    ext = client.post(f"/api/v1/links/{made['id']}/extend", json={"days": 5}, headers=h).json()
    assert ext["state"] == "active"
    assert client.post(f"/api/v1/links/{made['id']}/disable", json={}, headers=h).status_code == 422
    done = client.post(
        f"/api/v1/links/{made['id']}/disable", json={"second_click": True}, headers=h
    )
    assert done.json()["state"] == "disabled"
    assert client.post(f"/api/v1/links/{made['id']}/extend", json={}, headers=h).status_code == 409
    assert client.get("/api/v1/public/link", headers=tok(made["token"])).status_code == 404
    assert len(audit_rows(engine, "upload_link_disabled")) == 1


def test_unknown_expired_and_disabled_tokens_get_the_same_answer(
    client: TestClient, engine: Engine
) -> None:
    h = login(client, "asha")
    live, expired, disabled = (make_link(client, h) for _ in range(3))
    with engine.begin() as c:
        c.execute(
            text("UPDATE upload_links SET expires_at = now() - interval '1 minute' WHERE id = :i"),
            {"i": expired["id"]},
        )
    client.post(f"/api/v1/links/{disabled['id']}/disable", json={"second_click": True}, headers=h)
    answers = [
        client.get("/api/v1/public/link", headers=tok(t))
        for t in (expired["token"], disabled["token"], "x" * 32, "short", "")
    ]
    assert {(a.status_code, a.text) for a in answers} == {
        (404, '{"detail":"This link is not active."}')
    }
    assert client.get("/api/v1/public/link", headers=tok(live["token"])).status_code == 200
    assert (
        client.get(f"/api/v1/public/link?token={live['token']}").status_code == 404
    )  # header only


# --------------------------------------------------------------------------- the applicant's side
def test_the_page_reads_back_nothing_but_checklist_counts(
    client: TestClient, engine: Engine
) -> None:
    h = login(client, "asha")
    token = make_link(client, h, loan_type="personal")["token"]
    first = client.get("/api/v1/public/link", headers=tok(token)).json()
    assert first == {"active": True, "loan_type": "personal", "expires_on": first["expires_on"],
                     "request_open": True, "request_received": False, "accepting_files": False,
                     "sent": False, "checklist": None}  # fmt: skip
    assert (
        client.post("/api/v1/public/files", files=pfiles("a.pdf"), headers=tok(token)).status_code
        == 409
    )
    assert (
        client.post("/api/v1/public/request", json=REQUEST, headers=tok(token)).status_code == 200
    )
    out = client.post(
        "/api/v1/public/files", files=pfiles("my payslip.pdf", "junk.txt"), headers=tok(token)
    )
    body = out.json()
    assert out.status_code == 200 and out.headers["cache-control"] == "no-store"
    assert [(f["name"], f["result"]) for f in body["files"]] == [
        ("junk.txt", "not accepted"),
        ("my payslip.pdf", "received"),
    ]
    flat = json.dumps(body)
    for leak in (
        "payslip_clean",
        "score",
        "band",
        "recommend",
        "status",
        "case_no",
        "case-",
    ):
        assert leak not in flat.lower(), leak
    items = {
        i["type"]: (i["have"], i["needed"]) for p in body["checklist"]["people"] for i in p["items"]
    }
    assert items["pan_card"] == (0, 1) and items["payslip"] == (1, 3)
    again = client.get("/api/v1/public/link", headers=tok(token)).json()
    assert again["request_received"] and again["accepting_files"] and not again["sent"]
    assert set(again) == set(first)  # the same few keys; no case, no status, no outcome


def test_the_case_reaches_the_officer_as_from_applicant_and_send_needs_the_second_click(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha, ben = login(client, "asha"), login(client, "ben")
    made = make_link(client, asha)
    token = made["token"]
    assert (
        client.post(
            "/api/v1/public/request",
            json={k: v for k, v in REQUEST.items() if k != "loan_type"},
            headers=tok(token),
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/public/request", json=REQUEST, headers=tok(token)).status_code == 200
    )
    client.post("/api/v1/public/files", files=pfiles("p.pdf"), headers=tok(token))
    assert client.post("/api/v1/public/send", json={}, headers=tok(token)).status_code == 422
    sent = client.post(
        "/api/v1/public/send", json={"second_click": True}, headers=tok(token)
    ).json()
    assert re.fullmatch(r"PRM-[0-9A-F]{8}", sent["reference"]) and sent["incomplete"] is True
    rows = client.get("/api/v1/cases", headers=asha).json()
    assert (
        len(rows) == 1
        and rows[0]["origin"] == "applicant"
        and rows[0]["status"] == "applicant_submitted"
    )
    assert (
        rows[0]["applicant_sent"] is True and client.get("/api/v1/cases", headers=ben).json() == []
    )
    detail = client.get(f"/api/v1/cases/{rows[0]['id']}", headers=asha).json()
    assert (
        detail["origin"] == "applicant"
        and detail["intake_stage"]
        and detail["request_locked"] is False
    )
    assert detail["request"]["loan_amount"] == 250000 and detail["loan_amount"] == 250000
    assert client.get(f"/api/v1/cases/{rows[0]['id']}", headers=ben).status_code == 404
    # the link now belongs to the case, and the officer's listing says so without any token
    link = client.get("/api/v1/links", headers=asha).json()[0]
    assert link["case_no"] == detail["case_no"] and link["sent"] and token not in json.dumps(link)


def test_the_request_can_be_resent_until_the_officer_edits_the_form(client: TestClient) -> None:
    h = login(client, "asha")
    token = make_link(client, h)["token"]
    client.post("/api/v1/public/request", json=REQUEST, headers=tok(token))
    assert (
        client.post(
            "/api/v1/public/request", json={**REQUEST, "loan_amount": 300000}, headers=tok(token)
        ).status_code
        == 200
    )
    case = client.get("/api/v1/cases", headers=h).json()[0]
    assert (
        case["loan_amount"] == 300000 and len(client.get("/api/v1/cases", headers=h).json()) == 1
    )  # one case, not two


@needs_cases
def test_once_the_officer_saves_the_form_the_request_is_locked_and_the_link_takes_files_only(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case_name = first_clean_dev_case("PL")
    h = login(client, "asha")
    token = make_link(client, h)["token"]
    client.post("/api/v1/public/request", json=REQUEST, headers=tok(token))
    cid = client.get("/api/v1/cases", headers=h).json()[0]["id"]
    push(client, h, cid, as_files(case_files(case_name)))
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()
    body = desk_form(  # the officer corrects only the applicant's amount
        case_name, offer, loan_amount=275000,
        tenure_months=REQUEST["tenure_months"], purpose=REQUEST["purpose"],
    )  # fmt: skip
    saved = client.put(
        f"/api/v1/cases/{cid}/form", json={**body, "identity_confirmed": True}, headers=h
    )
    assert saved.status_code == 200, saved.text
    detail = client.get(f"/api/v1/cases/{cid}", headers=h).json()
    assert (
        detail["request_locked"]
        and detail["request"]["loan_amount"] == 250000
        and detail["loan_amount"] == 275000
    )
    assert audit_rows(engine, "request_corrected")[0].after == {"fields": ["loan_amount"]}
    locked = client.post("/api/v1/public/request", json=REQUEST, headers=tok(token))
    assert locked.status_code == 409 and "already received" in locked.json()["detail"]
    assert (
        client.post(
            "/api/v1/public/files", files=pfiles("late.pdf"), headers=tok(token)
        ).status_code
        == 200
    )


@needs_cases
def test_after_submit_the_link_refuses_files_neutrally_and_the_officer_sees_it(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case_name = first_clean_dev_case("PL")
    h = login(client, "asha")
    cid = start(client, h, "personal")
    push(client, h, cid, as_files(case_name and case_files(case_name)))
    say_employment(client, h, cid, case_name)
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()
    client.put(
        f"/api/v1/cases/{cid}/form",
        json={**desk_form(case_name, offer), "identity_confirmed": True},
        headers=h,
    )
    asked = client.post(
        f"/api/v1/cases/{cid}/ask-applicant", json={"second_click": True}, headers=h
    ).json()
    assert asked["new_link"] and asked["token"]
    assert (
        client.post(
            "/api/v1/public/files", files=pfiles("more.pdf"), headers=tok(asked["token"])
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/cases/{cid}/submit", headers=h).status_code == 202
    refused = client.post(
        "/api/v1/public/files", files=pfiles("later.pdf"), headers=tok(asked["token"])
    )
    assert refused.status_code == 409 and refused.json() == {
        "detail": "This link is not accepting files right now."
    }
    timeline = [a["action"] for a in client.get(f"/api/v1/cases/{cid}/audit", headers=h).json()]
    assert "applicant_upload_refused" in timeline
    # nothing under the running pipeline changed: the refused file was never stored
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM documents WHERE original_name = 'later.pdf'")
            ).scalar()
            == 0
        )


def test_ask_the_applicant_needs_the_second_click_and_keeps_the_same_link_open(
    client: TestClient, engine: Engine
) -> None:
    h = login(client, "asha")
    cid = start(client, h, "personal")
    url = f"/api/v1/cases/{cid}/ask-applicant"
    assert client.post(url, json={}, headers=h).status_code == 422
    first = client.post(url, json={"second_click": True}, headers=h).json()
    second = client.post(url, json={"second_click": True}, headers=h).json()
    assert (
        first["new_link"]
        and first["token"]
        and second
        == {"link_id": first["link_id"], "token": first["token"], "path": first["path"],
            "new_link": False}  # the sealed copy lets the owner see the same address again
    )
    assert (
        client.post(
            f"/api/v1/cases/{cid}/ask-applicant",
            json={"second_click": True},
            headers=login(client, "ben"),
        ).status_code
        == 404
    )
    # a link made from the officer's case takes files for that case and offers no request
    view = client.get("/api/v1/public/link", headers=tok(first["token"])).json()
    assert (
        view["request_open"] is False
        and view["accepting_files"] is True
        and view["loan_type"] == "personal"
    )
    assert (
        client.post("/api/v1/public/request", json=REQUEST, headers=tok(first["token"])).status_code
        == 409
    )


# --------------------------------------------------------------------------- abuse limits
def test_unsafe_archives_and_flooding_on_the_public_side(
    client: TestClient, engine: Engine
) -> None:
    import io
    import zipfile

    h = login(client, "asha")
    token = make_link(client, h)["token"]
    client.post("/api/v1/public/request", json=REQUEST, headers=tok(token))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.pdf", PAYSLIP)
    bad = client.post(
        "/api/v1/public/files",
        headers=tok(token),
        files=[("files", ("x.zip", buf.getvalue(), "application/zip"))],
    )
    assert bad.status_code == 422 and "outside" in bad.json()["detail"]
    s = client.app.state.settings  # type: ignore[attr-defined]
    s.link_max_files = 2
    ok = client.post("/api/v1/public/files", files=pfiles("a.pdf", "b.pdf"), headers=tok(token))
    assert ok.status_code == 200
    full = client.post("/api/v1/public/files", files=pfiles("c.pdf"), headers=tok(token))
    assert full.status_code == 409 and "more files" in full.json()["detail"]
    s.link_max_files = 80
    s.link_rate_per_minute = 3  # three requests a minute for this link
    client.app.state.limiter = RateLimiter()  # type: ignore[attr-defined]  # start the count again
    codes = [client.get("/api/v1/public/link", headers=tok(token)).status_code for _ in range(6)]
    assert codes[:1] == [200] and 429 in codes and codes[-1] == 429


def test_guessing_tokens_is_slowed_down_per_address(client: TestClient) -> None:
    codes = [
        client.get("/api/v1/public/link", headers=tok(f"guess-{i:02d}-" + "x" * 20)).status_code
        for i in range(25)
    ]
    assert set(codes) == {404, 429} and codes[0] == 404 and codes[-1] == 429


def test_the_token_never_reaches_a_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    h = login(client, "asha")
    token = make_link(client, h)["token"]
    client.post("/api/v1/public/request", json=REQUEST, headers=tok(token))
    client.post("/api/v1/public/files", files=pfiles("a.pdf"), headers=tok(token))
    client.get("/api/v1/public/link", headers=tok(token))
    assert token not in caplog.text


# --------------------------------------------------------------------------- the upload-link message
class Catcher:
    def __init__(self) -> None:
        self.sent: list[Outgoing] = []

    def send(self, message: Outgoing) -> None:
        self.sent.append(message)


def test_the_upload_link_message_carries_only_the_link_and_never_keeps_the_token(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    catcher = Catcher()
    client.app.state.sender = catcher  # type: ignore[attr-defined]
    h = login(client, "asha")
    cid = start(client, h, "personal")
    asked = client.post(
        f"/api/v1/cases/{cid}/ask-applicant", json={"second_click": True}, headers=h
    ).json()
    token, link_id = asked["token"], asked["link_id"]
    base = {
        "template": "upload_link",
        "recipient_email": "customer@example.test",
        "link_id": link_id,
        "link_token": token,
    }
    drafted = client.post(f"/api/v1/cases/{cid}/messages", json=base, headers=h)
    assert drafted.status_code == 201 and drafted.json()["status"] == "draft"
    m = drafted.json()
    assert "[your secure upload link]" in m["text"] and token not in json.dumps(m)
    assert (
        m["subject"] == "Pramaan: your secure upload link" and "documents" not in m["body"].lower()
    )
    url = f"/api/v1/messages/{m['id']}/send"
    assert client.post(url, json={}, headers=h).status_code == 422  # the second click
    assert (
        client.post(url, json={"second_click": True}, headers=h).status_code == 422
    )  # and the token again
    assert (
        client.post(url, json={"second_click": True, "link_token": "z" * 30}, headers=h).status_code
        == 422
    )
    sent = client.post(url, json={"second_click": True, "link_token": token}, headers=h)
    assert sent.status_code == 200 and sent.json()["status"] == "sent"
    out = catcher.sent[0].text
    assert f"/u#{token}" in out and out.count("http") == 1 and "Pramaan staff will never ask" in out
    with engine.connect() as c:
        kept = c.execute(text("SELECT final_text, body, link_id::text FROM outbox")).one()
        audit = json.dumps(
            [dict(r._mapping) for r in c.execute(text("SELECT * FROM audit_log"))], default=str
        )
    assert (
        token not in kept.final_text
        and token not in kept.body
        and kept.link_id == link_id
        and token not in audit
    )


def test_the_link_message_checks_catch_a_second_link_a_foreign_link_and_other_templates(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    client.app.state.sender = Catcher()  # type: ignore[attr-defined]
    asha, ben = login(client, "asha"), login(client, "ben")
    cid, other = start(client, asha, "personal"), start(client, ben, "personal")
    asked = client.post(
        f"/api/v1/cases/{cid}/ask-applicant", json={"second_click": True}, headers=asha
    ).json()
    other_link = client.post(
        f"/api/v1/cases/{other}/ask-applicant", json={"second_click": True}, headers=ben
    ).json()
    base = {
        "template": "upload_link",
        "recipient_email": "c@example.test",
        "link_id": asked["link_id"],
        "link_token": asked["token"],
    }
    url = f"/api/v1/cases/{cid}/messages"
    blocked = client.post(
        url, json={**base, "body": "Please use https://evil.example/login instead."}, headers=asha
    )
    assert (
        blocked.status_code == 201
        and blocked.json()["status"] == "blocked"
        and "link" in blocked.json()["block_reason"].lower()
    )
    # another officer's link, a link of another case, or a missing token cannot be used here
    assert (
        client.post(
            url,
            json={**base, "link_id": other_link["link_id"], "link_token": other_link["token"]},
            headers=asha,
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, json={k: v for k, v in base.items() if k != "link_token"}, headers=asha
        ).status_code
        == 422
    )
    # the early statuses are for this template only
    assert (
        client.post(
            url,
            json={"template": "general_contact", "recipient_email": "c@example.test"},
            headers=asha,
        ).status_code
        == 409
    )
    with engine.begin() as c:
        c.execute(text("UPDATE cases SET status = 'confirmed' WHERE id = :i"), {"i": cid})
    # no other template may carry a link
    assert (
        client.post(
            url,
            json={
                "template": "general_contact",
                "recipient_email": "c@example.test",
                "link_id": asked["link_id"],
            },
            headers=asha,
        ).status_code
        == 422
    )
