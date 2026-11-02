"""Customer contact messages and issue reports (Stage 9): the content check on every forbidden
pattern, the templates, the server-side flow (draft, edit, second click, send, fail, retry), roles
and ownership, audit rows, and the issue inbox. The sender is a stand-in; the database is a
throwaway one (see test_api.py for the fixtures)."""

# ruff: noqa: F811 - pytest fixtures imported from test_api are redefined as arguments
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.notifications import templates
from app.notifications.check import check_issue_text, check_message
from app.notifications.sender import ConsoleSender, Outgoing, SendError
from tests.test_api import PASSWORD, client, create, engine, login, minimal  # noqa: F401

CONTACT = ["Officer: Asha Officer", "Email: asha@example.test"]


def final_of(body: str) -> str:
    return templates.compose(body, CONTACT, None)


def problems(body: str, names: list[str] | None = None) -> list[str]:
    return check_message(templates.SUBJECT, body, final_text=final_of(body), names=names)


# --------------------------------------------------------------------------- the content check
@pytest.mark.parametrize("code", ["general_contact", "contact_soon", "visit_branch"])
def test_every_template_passes_the_check(code: str) -> None:
    assert problems(templates.TEMPLATES[code].body, ["Rahul Sharma"]) == []


def test_a_plain_blank_message_passes_and_an_empty_one_does_not() -> None:
    assert problems("Please call me back when you are free.") == []
    assert "The message is empty" in problems("   ")


@pytest.mark.parametrize(
    ("text_in", "reason"),
    [
        ("Your PAN ABCDE1234F is on file", "PAN"),
        ("pan abcde1234f", "PAN"),
        ("Aadhaar 2345 6789 0123", "Aadhaar"),
        ("Aadhaar XXXX XXXX 1234", "Aadhaar"),
        ("Call me on 9876543210", "phone number"),
        ("Call +91 98765 43210", "phone number"),
        ("Account 123456789012", "account number"),
        ("see https://pramaan.example/x", "link"),
        ("see www.pramaan.example", "link"),
        ("write to me@evil.example", "email address"),
        ("loan of Rs. 5,00,000", "amount of money"),
        ("a loan of ₹500000", "amount of money"),
        ("we offer 12 lakh", "amount of money"),
        ("Your score is 72", "score"),
        ("you got 72 out of 100", "score"),
        ("rule CM-KYC-01 failed", "rule"),
        ("your FOIR is high", "score"),
        ("Your loan is approved", "result"),
        ("The loan was rejected", "result"),
        ("You are eligible", "result"),
        ("not eligible", "result"),
        ("we recommend a visit", "result"),
        ("Your case is referred", "result"),
        ("A payslip is missing", "missing item"),
        ("Please bring your bank statement", "missing item"),
        ("an incomplete form", "missing item"),
        ("Share your OTP", "OTP"),
        ("Tell me your PIN", "OTP"),
        ("send your password", "OTP"),
        ("your CVV please", "OTP"),
        ("card number please", "OTP"),
    ],
)
def test_each_forbidden_pattern_blocks_the_message(text_in: str, reason: str) -> None:
    found = problems(text_in)
    assert found, text_in
    assert any(reason.lower() in f.lower() for f in found), (text_in, found)


def test_the_postal_pin_code_is_not_a_credential_request() -> None:
    assert not any("OTP" in r for r in problems("Visit the branch in your pin code area."))


def test_the_customers_name_is_blocked_whole_or_in_part() -> None:
    assert "Contains the customer's name" in problems(
        "Dear Rahul Sharma, please call.", ["Rahul Sharma"]
    )
    assert "Contains the customer's name" in problems("Dear sharma, please call.", ["Rahul Sharma"])
    assert problems("Dear customer, please call.", ["Rahul Sharma"]) == []


def test_a_message_without_the_footer_is_blocked() -> None:
    found = check_message(templates.SUBJECT, "Please call.", final_text="Please call.")
    assert "The fraud warning is missing" in found


def test_the_footer_is_added_by_code_and_says_staff_never_ask_for_credentials() -> None:
    final = final_of("Please call.")
    assert templates.FOOTER in final and "never ask you for your OTP, PIN or password" in final


def test_issue_text_blocks_personal_data_only() -> None:
    assert check_issue_text("The page froze when I saved the case") == []
    assert check_issue_text("The payslip upload failed, rule CM-KYC-01 looked wrong") == []
    assert check_issue_text("PAN ABCDE1234F failed")
    assert check_issue_text("customer 9876543210 not found")
    assert check_issue_text("account 123456789012")
    assert check_issue_text("mail a@b.example")


def test_console_sender_prints_the_message_with_a_masked_recipient(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleSender().send(Outgoing("m1", "customer@example.test", "S", "Body text"))
    out = capsys.readouterr().out
    assert "Body text" in out and "****@example.test" in out and "customer@" not in out


# --------------------------------------------------------------------------- the API


class Flaky:
    """A sender that fails until `ok` is set."""

    def __init__(self) -> None:
        self.ok = False
        self.sent: list[Outgoing] = []

    def send(self, message: Outgoing) -> None:
        if not self.ok:
            raise SendError("mail server unavailable")
        self.sent.append(message)


@pytest.fixture
def flaky(client: TestClient) -> Iterator[Flaky]:
    sender = Flaky()
    client.app.state.sender = sender  # type: ignore[attr-defined]
    yield sender


def done_case(
    client: TestClient, engine: Engine, who: str = "asha", **over: Any
) -> tuple[str, dict[str, str]]:
    h = login(client, who)
    body = minimal()
    body["applicants"][0]["email"] = over.pop("email", "customer@example.test")
    case_id = create(client, h, body)
    with engine.begin() as c:
        c.execute(text("UPDATE cases SET status = :s WHERE id = :i"),
                  {"s": over.pop("status", "confirmed"), "i": case_id})  # fmt: skip
    return case_id, h


def draft(client: TestClient, h: dict[str, str], case_id: str, **body: Any) -> Any:
    return client.post(f"/api/v1/cases/{case_id}/messages", headers=h,
                       json={"template": "general_contact", **body})  # fmt: skip


def actions(engine: Engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("SELECT action FROM audit_log ORDER BY at, id"))]


@pytest.mark.db
def test_draft_edit_send_needs_the_second_click_and_lands_in_sent_items(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine)
    flaky.ok = True
    r = draft(client, h, case_id, include_case_ref=True)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["status"] == "draft" and m["recipient"] == "****@example.test"
    assert templates.FOOTER in m["text"] and "Officer: Asha Officer" in m["text"]
    assert re.search(r"Reference: CASE-\d{4}-\d{4}", m["text"])
    assert not re.search(r"Test Person|score|approve", m["text"], re.I)

    url = f"/api/v1/messages/{m['id']}"
    e = client.put(
        url, headers=h, json={"body": "Hello, please call me back.", "include_case_ref": False}
    )
    assert e.status_code == 200 and "Reference:" not in e.json()["text"]

    assert client.post(f"{url}/send", headers=h, json={}).status_code == 422  # no second click
    assert client.post(f"{url}/send", headers=h, json={"second_click": False}).status_code == 422
    assert not flaky.sent
    ok = client.post(f"{url}/send", headers=h, json={"second_click": True})
    assert ok.status_code == 200 and ok.json()["status"] == "sent" and len(flaky.sent) == 1
    assert flaky.sent[0].recipient == "customer@example.test"
    assert templates.FOOTER in flaky.sent[0].text
    assert client.post(f"{url}/send", headers=h, json={"second_click": True}).status_code == 409
    assert client.put(url, headers=h, json={"body": "x"}).status_code == 409  # sent is final

    items = client.get("/api/v1/messages", headers=h).json()
    assert [i["status"] for i in items] == ["sent"] and items[0]["case_no"].startswith("CASE-")
    assert client.get(f"/api/v1/cases/{case_id}/messages", headers=h).json()[0]["id"] == m["id"]
    assert {"message_drafted", "message_edited", "message_sent"} <= set(actions(engine))


@pytest.mark.db
def test_blocked_text_is_never_sent_even_if_the_ui_skips_the_check(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine)
    flaky.ok = True
    r = draft(client, h, case_id, template="blank", body="Your loan is approved, score 90")
    assert r.status_code == 201 and r.json()["status"] == "blocked"
    assert "result of the assessment" in r.json()["block_reason"]
    url = f"/api/v1/messages/{r.json()['id']}"
    s = client.post(f"{url}/send", headers=h, json={"second_click": True})
    assert s.status_code == 422 and s.json()["reasons"] and not flaky.sent
    fixed = client.put(url, headers=h, json={"body": "Please call me."})
    assert fixed.json()["status"] == "draft" and fixed.json()["block_reason"] is None
    assert client.post(f"{url}/send", headers=h, json={"second_click": True}).status_code == 200
    assert "message_blocked" in actions(engine)


@pytest.mark.db
def test_a_message_with_the_customer_name_is_blocked_and_default_text_has_no_case_data(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine)
    named = draft(client, h, case_id, template="blank", body="Dear Test Person, please call.")
    assert named.json()["status"] == "blocked"
    for code in ("general_contact", "contact_soon", "visit_branch"):
        ok = draft(client, h, case_id, template=code)
        text_out = ok.json()["text"]
        assert ok.json()["status"] == "draft"
        assert not re.search(r"Test Person|ABCDE|1234|9876543210|50000|score", text_out)


@pytest.mark.db
def test_failed_sends_are_shown_failed_and_can_be_retried(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine)
    m = draft(client, h, case_id).json()
    url = f"/api/v1/messages/{m['id']}"
    bad = client.post(f"{url}/send", headers=h, json={"second_click": True})
    assert bad.status_code == 502 and "failed" in bad.json()["detail"]
    got = client.get(url, headers=h).json()
    assert got["status"] == "failed" and got["error"] == "mail server unavailable"
    flaky.ok = True
    again = client.post(f"{url}/send", headers=h, json={"second_click": True})
    assert again.status_code == 200 and again.json()["status"] == "sent"
    assert {"message_failed", "message_sent"} <= set(actions(engine))


@pytest.mark.db
def test_a_case_that_is_not_finished_or_has_no_email_cannot_get_a_message(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine, status="awaiting_confirmation")
    assert draft(client, h, case_id).status_code == 409
    no_mail = create(client, h, minimal())
    with engine.begin() as c:
        c.execute(text("UPDATE cases SET status = 'stopped' WHERE id = :i"), {"i": no_mail})
    assert draft(client, h, no_mail).status_code == 422
    typed = draft(client, h, no_mail, recipient_email="typed@example.test")
    assert typed.status_code == 201  # a stopped run may be contacted too
    assert draft(client, h, no_mail, recipient_email="not-an-email").status_code == 422


@pytest.mark.db
def test_messages_are_private_to_their_officer_and_closed_to_the_admin(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, asha = done_case(client, engine)
    ben, ada = login(client, "ben"), login(client, "ada")
    m = draft(client, asha, case_id).json()
    url = f"/api/v1/messages/{m['id']}"
    assert client.get(url, headers=ben).status_code == 404
    assert client.put(url, headers=ben, json={"body": "x"}).status_code == 404
    assert client.post(f"{url}/send", headers=ben, json={"second_click": True}).status_code == 404
    assert client.get("/api/v1/messages", headers=ben).json() == []
    assert draft(client, ben, case_id).status_code == 404  # not their case
    assert client.get(f"/api/v1/cases/{case_id}/messages", headers=ben).status_code == 404
    for path in ("/messages", f"/messages/{m['id']}", "/messages/templates"):
        assert client.get(f"/api/v1{path}", headers=ada).status_code == 403
    assert draft(client, ada, case_id).status_code == 403
    assert client.get("/api/v1/messages").status_code == 401


@pytest.mark.db
def test_templates_endpoint_and_officer_phone(client: TestClient, engine: Engine) -> None:
    h = login(client, "asha")
    t = client.get("/api/v1/messages/templates", headers=h).json()
    assert [x["code"] for x in t["templates"]] == [
        "general_contact",
        "contact_soon",
        "visit_branch",
        "blank",
    ]
    assert t["footer"] == templates.FOOTER and t["phone_set"] is False
    assert (
        client.put("/api/v1/profile/phone", headers=h, json={"phone": "12345"}).status_code == 422
    )
    assert (
        client.put("/api/v1/profile/phone", headers=h, json={"phone": "9123456780"}).status_code
        == 200
    )
    t = client.get("/api/v1/messages/templates", headers=h).json()
    assert t["phone_set"] is True and "Phone: 9123456780" in t["contact"]
    assert "user_phone_changed" in actions(engine)


@pytest.mark.db
def test_customer_email_is_masked_in_the_case_view_and_kept_when_correcting(
    client: TestClient,
    engine: Engine,
) -> None:
    case_id, h = done_case(client, engine)
    view = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert view["applicants"][0]["email"] == "****@example.test"
    assert "customer@" not in str(view)
    with engine.connect() as c:  # kept out of the form the pipeline reads
        form = c.execute(
            text("SELECT form_data FROM cases WHERE id = :i"), {"i": case_id}
        ).scalar_one()
    assert "email" not in form["applicants"][0]
    body = minimal()
    body["applicants"][0]["email"] = "****@example.test"
    with engine.begin() as c:
        c.execute(
            text("UPDATE cases SET status='stopped', stop_class='fix' WHERE id = :i"),
            {"i": case_id},
        )
    assert (
        client.post(f"/api/v1/cases/{case_id}/resume", headers=h, json={"case": body}).status_code
        != 422
    )
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT email FROM applicants WHERE case_id = :i"), {"i": case_id}
            ).scalar_one()
            == "customer@example.test"
        )


@pytest.mark.db
def test_admin_summary_counts_messages_and_issues_but_nothing_more(
    client: TestClient,
    engine: Engine,
    flaky: Flaky,
) -> None:
    case_id, h = done_case(client, engine)
    flaky.ok = True
    m = draft(client, h, case_id).json()
    client.post(f"/api/v1/messages/{m['id']}/send", headers=h, json={"second_click": True})
    client.post(
        "/api/v1/issues", headers=h, json={"category": "bug", "body": "The page froze twice."}
    )
    s = client.get("/api/v1/admin/summary", headers=login(client, "ada")).json()
    assert s["messages_sent"] == 1 and s["open_issues"] == 1 and s["messages_failed"] == 0


# --------------------------------------------------------------------------- issue reports
@pytest.mark.db
def test_an_issue_is_filed_read_and_closed_with_audit_rows(
    client: TestClient, engine: Engine
) -> None:
    asha, ben, ada = login(client, "asha"), login(client, "ben"), login(client, "ada")
    r = client.post("/api/v1/issues", headers=asha, json={
        "category": "wrong_result", "case_ref": "CASE-2026-0001", "body": "The stepper shows the wrong stage."})  # fmt: skip
    assert r.status_code == 201 and r.json()["status"] == "open"
    iid = r.json()["id"]
    assert [i["id"] for i in client.get("/api/v1/issues", headers=asha).json()] == [iid]
    assert client.get("/api/v1/issues", headers=ben).json() == []
    inbox = client.get("/api/v1/admin/issues", headers=ada).json()
    assert [i["id"] for i in inbox] == [iid] and inbox[0]["reporter"] == "Asha Officer"
    read = client.post(f"/api/v1/admin/issues/{iid}/read", headers=ada).json()
    assert read["status"] == "read" and read["read_at"]
    closed = client.post(f"/api/v1/admin/issues/{iid}/close", headers=ada).json()
    assert closed["status"] == "closed"
    assert client.get("/api/v1/admin/issues?status=open", headers=ada).json() == []
    assert {"issue_filed", "issue_read", "issue_closed"} <= set(actions(engine))
    assert client.get("/api/v1/admin/issues?status=odd", headers=ada).status_code == 422


@pytest.mark.db
def test_an_issue_with_personal_data_is_refused_and_not_stored(
    client: TestClient, engine: Engine
) -> None:
    h = login(client, "asha")
    for leak in (
        "PAN ABCDE1234F was wrong",
        "call 9876543210 now",
        "a/c 123456789012 failed",
        "mail x@y.example please",
    ):
        r = client.post("/api/v1/issues", headers=h, json={"category": "bug", "body": leak})
        assert r.status_code == 422 and "personal details" in r.json()["detail"], leak
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM issue_reports")).scalar_one() == 0
    assert "issue_blocked" in actions(engine)
    short = client.post("/api/v1/issues", headers=h, json={"category": "bug", "body": "bad"})
    assert short.status_code == 422
    bad_ref = client.post(
        "/api/v1/issues",
        headers=h,
        json={"category": "bug", "case_ref": "x", "body": "long enough text"},
    )
    assert bad_ref.status_code == 422


@pytest.mark.db
def test_issue_routes_are_role_split(client: TestClient, engine: Engine) -> None:
    asha, ada = login(client, "asha"), login(client, "ada")
    body = {"category": "other", "body": "Something odd happened."}
    iid = client.post("/api/v1/issues", headers=asha, json=body).json()["id"]
    assert client.post("/api/v1/issues", headers=ada, json=body).status_code == 403
    assert client.get("/api/v1/issues", headers=ada).status_code == 403
    for path in ("", f"/{iid}/read", f"/{iid}/close"):
        method = client.get if path == "" else client.post
        assert method(f"/api/v1/admin/issues{path}", headers=asha).status_code == 403
    assert (
        client.post(
            f"/api/v1/admin/issues/{iid.replace(iid[:4], '0000')}/read", headers=ada
        ).status_code
        == 404
    )
    assert "case" not in str(client.get("/api/v1/admin/issues", headers=ada).json()).replace(
        "case_ref", ""
    )
