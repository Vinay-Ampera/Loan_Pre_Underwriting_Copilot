"""The HTTP API (Stage 6): sign-in and lockout, roles enforced on the server, validation, upload
checks, confirm and override rules, the admin precedent queue, the PDF, and one full case per loan
type driven over HTTP exactly as the browser does. Models are off (code writes the text), the
embedder is the test fake, checkpoints are in memory; the database is a throwaway one."""

import json
import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from alembic import command
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text

from app.api.main import create_app
from app.api.security import hash_password
from app.core.config import REPO_ROOT, Settings
from app.db.migrate import alembic_config
from app.rag.index import reindex
from app.rag.retrieve import PolicyRetriever
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"
PASSWORD = "correct horse battery"
pytestmark = pytest.mark.db
needs_cases = pytest.mark.skipif(
    not (OUTPUT / "cases").exists(), reason="run python -m synthetic.generate"
)


# --------------------------------------------------------------------------- fixtures
@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        reindex(conn, embed=fake_embed_passages)
        for name, role in (
            ("Asha Officer", "officer"),
            ("Ben Officer", "officer"),
            ("Ada Admin", "admin"),
        ):
            email = f"{name.split()[0].lower()}@example.test"
            conn.execute(
                text(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)"
                ),
                {"n": name, "e": email, "h": hash_password(PASSWORD), "r": role},
            )
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("test-secret-" + "x" * 32),
        upload_dir=tmp_path / "uploads",
        login_max_failures=3,
    )
    app = create_app(
        settings,
        engine=engine,
        saver=InMemorySaver(),
        use_llm=False,
        embed=fake_embed_passages,
        ctx_kwargs={
            "retriever_factory": lambda c: PolicyRetriever(
                c, embed=fake_vector, rerank_fn=fake_rerank
            )
        },
    )
    with TestClient(app) as c:
        yield c


def login(client: TestClient, who: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login", json={"email": f"{who}@example.test", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def application(case: str) -> dict[str, Any]:
    app = json.loads((OUTPUT / "cases" / case / "application.json").read_text())
    app.pop("case_id")
    return app


def minimal(loan_type: str = "personal", **over: Any) -> dict[str, Any]:
    person = {
        "role": "primary", "full_name": "Test Person", "dob": "1990-01-01", "pan": "ABCDE1234F",
        "aadhaar_last4": "1234", "address": "1 Test Street, Pune", "phone": "9876543210",
        "employment_type": "salaried", "declared_monthly_income": 50000,
    }  # fmt: skip
    return {
        "loan_type": loan_type,
        "loan_amount": 100000,
        "tenure_months": 24,
        "applicants": [person],
        **over,
    }


def create(client: TestClient, headers: dict[str, str], body: dict[str, Any]) -> str:
    r = client.post("/api/v1/cases", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


# --------------------------------------------------------------------------- sign-in
def test_login_returns_a_token_and_wrong_credentials_get_one_message(client: TestClient) -> None:
    h = login(client, "asha")
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["role"] == "officer" and "password" not in json.dumps(me)
    bad = client.post("/api/v1/auth/login", json={"email": "asha@example.test", "password": "nope"})
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "who@example.test", "password": "nope"}
    )
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()


def test_repeated_failures_lock_the_account_and_are_audited(
    client: TestClient, engine: Engine
) -> None:
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "ben@example.test", "password": "x"}
            ).status_code
            == 401
        )
    good = client.post(
        "/api/v1/auth/login", json={"email": "ben@example.test", "password": PASSWORD}
    )
    assert good.status_code == 423  # locked, even with the right password
    with engine.connect() as c:
        actions = [r[0] for r in c.execute(text("SELECT action FROM audit_log ORDER BY at"))]
    assert (
        actions.count("login_failed") == 2
        and "login_locked" in actions
        and "login_blocked" in actions
    )


def test_missing_bad_and_expired_tokens_are_refused(client: TestClient, engine: Engine) -> None:
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get("/api/v1/cases", headers={"Authorization": "Bearer junk"}).status_code == 401
    h = login(client, "asha")
    with engine.begin() as c:
        c.execute(text("UPDATE users SET active = false WHERE email = 'asha@example.test'"))
    assert client.get("/api/v1/cases", headers=h).status_code == 401  # deactivated at once


# --------------------------------------------------------------------------- roles
def test_admin_cannot_create_upload_submit_or_confirm(client: TestClient) -> None:
    officer, admin = login(client, "asha"), login(client, "ada")
    case_id = create(client, officer, minimal())
    assert client.post("/api/v1/cases", json=minimal(), headers=admin).status_code == 403
    pdf = ("a.pdf", b"%PDF-1.4", "application/pdf")
    up = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"files": pdf},
        data={"role": "primary"},
        headers=admin,
    )
    assert up.status_code == 403
    for path in ("submit", "resume", "confirm", "override"):
        r = client.post(
            f"/api/v1/cases/{case_id}/{path}", json={"second_click": True}, headers=admin
        )
        assert r.status_code == 403, path
    assert client.get("/api/v1/cases", headers=admin).status_code == 403
    assert client.get(f"/api/v1/cases/{case_id}", headers=admin).status_code == 403


def test_officer_cannot_reach_the_precedent_queue(client: TestClient, engine: Engine) -> None:
    officer = login(client, "asha")
    pid = add_precedent(engine)
    assert client.get("/api/v1/admin/precedents", headers=officer).status_code == 403
    assert (
        client.post(f"/api/v1/admin/precedents/{pid}/approve", json={}, headers=officer).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/admin/precedents/{pid}/reject", json={}, headers=officer).status_code
        == 403
    )
    with engine.connect() as c:
        assert c.execute(text("SELECT status FROM precedents")).scalar_one() == "pending"


def test_an_officer_sees_only_their_own_cases(client: TestClient) -> None:
    asha, ben = login(client, "asha"), login(client, "ben")
    case_id = create(client, asha, minimal())
    assert client.get(f"/api/v1/cases/{case_id}", headers=ben).status_code == 404
    assert client.get("/api/v1/cases", headers=ben).json() == []
    assert [c["id"] for c in client.get("/api/v1/cases", headers=asha).json()] == [case_id]
    assert client.post(f"/api/v1/cases/{case_id}/submit", headers=ben).status_code == 404


# --------------------------------------------------------------------------- the form
def test_case_form_rules_follow_the_loan_type(client: TestClient) -> None:
    h = login(client, "asha")
    post = lambda body: client.post("/api/v1/cases", json=body, headers=h)  # noqa: E731
    assert post(minimal("education")).status_code == 422  # a co-applicant is mandatory
    co = {**minimal()["applicants"][0], "role": "co"}
    assert (
        post({**minimal("personal"), "applicants": [minimal()["applicants"][0], co]}).status_code
        == 422
    )
    assert post(minimal("home")).status_code == 422  # loan details missing
    bad_pan = minimal()
    bad_pan["applicants"][0]["pan"] = "123"
    assert post(bad_pan).status_code == 422
    assert post({**minimal(), "application_date": "2999-01-01"}).status_code == 422
    r = client.get("/api/v1/meta/loan-types", headers=h).json()
    assert r["co_applicant"]["education"] == "required" and r["fields"]["personal"] == []


def test_identifiers_are_masked_in_the_case_view(client: TestClient) -> None:
    h = login(client, "asha")
    view = client.get(f"/api/v1/cases/{create(client, h, minimal())}", headers=h)
    body = view.text
    assert "ABCDE1234F" not in body and "9876543210" not in body
    a = view.json()["applicants"][0]
    assert (
        a["pan"] == "ABCDE****F" and a["aadhaar"] == "XXXX XXXX 1234" and a["phone"] == "******3210"
    )


def test_masked_values_are_refused_on_create_and_kept_when_correcting(client: TestClient) -> None:
    from fastapi import HTTPException

    from app.api.cases import _merge_masked
    from app.api.schemas import CaseIn

    h = login(client, "asha")
    masked = minimal()
    masked["applicants"][0]["pan"] = "ABCDE****F"
    assert client.post("/api/v1/cases", json=masked, headers=h).status_code == 422
    biz = {**minimal("business"), "loan_details": {"gstin": "08PPIPM****"}}
    assert client.post("/api/v1/cases", json=biz, headers=h).status_code == 422

    stored = minimal()["applicants"]
    body = CaseIn.model_validate(
        {
            **minimal(),
            "loan_details": {},
            "applicants": [{**stored[0], "pan": "ABCDE****F", "phone": "******3210"}],
        }
    )
    _merge_masked(body, stored, {})
    assert (body.applicants[0].pan, body.applicants[0].phone) == ("ABCDE1234F", "9876543210")
    body.applicants[0].pan = "ZZZZZ****Z"  # a mask that is not the stored one is refused
    with pytest.raises(HTTPException):
        _merge_masked(body, stored, {})
    body.applicants[0].pan = "ABCDE1234F"
    body.loan_details = {"gstin": "08PPIPM****"}
    _merge_masked(body, stored, {"gstin": "08PPIPM4603I9Z7"})
    assert body.loan_details["gstin"] == "08PPIPM4603I9Z7"


# --------------------------------------------------------------------------- uploads
def blank_image(fmt: str) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), (128, 128, 128)).save(buf, fmt)
    return buf.getvalue()


def test_each_file_gets_its_own_result_and_rejected_files_are_never_kept(
    client: TestClient, engine: Engine, tmp_path: Path
) -> None:  # fmt: skip
    h = login(client, "asha")
    case_id = create(client, h, minimal())
    import pikepdf

    locked = tmp_path / "locked.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.save(locked, encryption=pikepdf.Encryption(owner="o", user="u"))
    files = [
        ("files", ("notes.txt", b"hello", "text/plain")),
        ("files", ("locked.pdf", locked.read_bytes(), "application/pdf")),
        ("files", ("flat.jpg", blank_image("JPEG"), "image/jpeg")),
        ("files", ("empty.pdf", b"", "application/pdf")),
    ]
    r = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files=files,
        data={"role": "primary", "doc_type": "pan_card"},
        headers=h,
    )
    assert r.status_code == 200
    got = {x["name"]: x for x in r.json()["results"]}
    assert (
        got["notes.txt"]["code"] == "bad_type" and got["locked.pdf"]["code"] == "password_protected"
    )
    assert got["flat.jpg"]["code"] == "blurry" and got["empty.pdf"]["code"] == "empty"
    assert all(x["status"] == "rejected" and x["message"] for x in got.values())
    stored = list((tmp_path / "uploads").rglob("*")) if (tmp_path / "uploads").exists() else []
    assert [p for p in stored if p.is_file()] == []  # nothing was written
    with engine.connect() as c:  # the rows stay, with the reason
        rows = c.execute(text("SELECT status, reject_reason FROM documents")).all()
    assert len(rows) == 4 and {r.status for r in rows} == {"rejected"}


@needs_cases
def test_good_files_are_accepted_checklist_updates_and_submit_needs_kyc(
    client: TestClient, tmp_path: Path
) -> None:
    h = login(client, "asha")
    case_id = create(client, h, {**application("SYN-PL-D01")})
    r = client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert r.status_code == 422 and "pan_card" in r.json()["detail"]
    folder = OUTPUT / "cases" / "SYN-PL-D01" / "documents" / "primary"
    for name, kind in (("pan_card.jpg", "pan_card"), ("aadhaar.jpg", "aadhaar")):
        up = client.post(
            f"/api/v1/cases/{case_id}/documents",
            data={"role": "primary", "doc_type": kind},
            headers=h,
            files={"files": (name, (folder / name).read_bytes(), "image/jpeg")},
        )
        assert up.json()["results"][0]["status"] in ("accepted", "warning")
    detail = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert detail["status"] == "uploaded"
    by_type = {c["type"]: c for c in detail["checklist"] if c["applicant"] == "primary"}
    assert by_type["pan_card"]["met"] and by_type["aadhaar"]["met"]
    assert not by_type["photo"]["met"] and detail["kyc_ready"] is False  # the photo is KYC too
    stored = [p for p in (tmp_path / "uploads").rglob("*") if p.is_file()]
    assert len(stored) == 2 and all(re.fullmatch(r"[0-9a-f]{32}\.jpg", p.name) for p in stored)
    doc = detail["documents"][0]
    served = client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/file", headers=h)
    assert served.status_code == 200 and served.headers["x-content-type-options"] == "nosniff"
    gone = client.delete(f"/api/v1/cases/{case_id}/documents/{doc['id']}", headers=h)
    assert (
        gone.status_code == 204
        and len([p for p in (tmp_path / "uploads").rglob("*") if p.is_file()]) == 1
    )


# --------------------------------------------------------------------------- precedent queue
def add_precedent(engine: Engine, status: str = "pending") -> str:
    with engine.begin() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = 'asha@example.test'")).scalar_one()
        case = c.execute(
            text("""INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months)
                    VALUES (:n, 'personal', :u, 1000, 12) RETURNING id"""),
            {"n": f"CASE-2026-{uuid.uuid4().int % 9000 + 1000}", "u": uid},
        ).scalar_one()
        return str(c.execute(
            text("""INSERT INTO precedents (source_case_id, status, loan_type, rule_ids, original_score,
                        original_recommendation, final_decision, officer_reason, report_summary, proposed_by)
                    VALUES (:c, :s, 'personal', '{PL-FOIR-01,PL-CIBIL-01}', 72, 'refer', 'approve',
                            'Stable employer and a clean repayment history.', 'Borderline FOIR.', :u)
                    RETURNING id"""), {"c": case, "s": status, "u": uid}).scalar_one())  # fmt: skip


def test_admin_approves_with_expiry_and_embedding_and_cannot_approve_twice(
    client: TestClient, engine: Engine
) -> None:
    admin = login(client, "ada")
    pid = add_precedent(engine)
    queue = client.get("/api/v1/admin/precedents", headers=admin).json()
    assert [q["id"] for q in queue] == [pid] and queue[0]["officer_reason"].startswith("Stable")
    too_far = client.post(
        f"/api/v1/admin/precedents/{pid}/approve", json={"valid_until": "2999-01-01"}, headers=admin
    )
    assert too_far.status_code == 422
    ok = client.post(f"/api/v1/admin/precedents/{pid}/approve", json={}, headers=admin)
    assert ok.status_code == 200
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT status, reviewed_by, reviewed_at, valid_until, embedding IS NOT NULL AS emb FROM precedents"
            )
        ).one()
        assert row.status == "approved" and row.reviewed_by and row.valid_until and row.emb
        assert (
            c.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'precedent_approved'")
            ).scalar_one()
            == 1
        )
    assert (
        client.post(f"/api/v1/admin/precedents/{pid}/approve", json={}, headers=admin).status_code
        == 409
    )


def test_reject_and_held_precedents(client: TestClient, engine: Engine) -> None:
    admin = login(client, "ada")
    a, held = add_precedent(engine), add_precedent(engine, "held")
    assert (
        client.post(
            f"/api/v1/admin/precedents/{a}/reject", json={"note": "too thin"}, headers=admin
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/admin/precedents/{held}/approve", json={}, headers=admin).status_code
        == 409
    )
    assert client.get("/api/v1/admin/precedents", headers=admin).json() == []  # nothing pending
    assert len(client.get("/api/v1/admin/precedents?status=all", headers=admin).json()) == 2


# --------------------------------------------------------------------------- whole cases
def upload_all(client: TestClient, h: dict[str, str], case_id: str, case: str) -> None:
    detail = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    known = set(detail["doc_types"])
    for role in ("primary", "co"):
        folder = OUTPUT / "cases" / case / "documents" / role
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            stem = re.sub(r"[_-]\d.*$", "", f.stem)
            kind = stem if stem in known else "other"
            mime = (
                "application/pdf"
                if f.suffix == ".pdf"
                else "image/jpeg"
                if f.suffix in (".jpg", ".jpeg")
                else "image/png"
            )
            r = client.post(
                f"/api/v1/cases/{case_id}/documents",
                data={"role": role, "doc_type": kind},
                headers=h,
                files={"files": (f.name, f.read_bytes(), mime)},
            )
            assert r.status_code == 200, r.text
            assert r.json()["results"][0]["status"] != "rejected", (f.name, r.json())


def wait_for(
    client: TestClient, h: dict[str, str], case_id: str, want: set[str], seconds: int = 400
) -> dict[str, Any]:
    end = time.time() + seconds
    while time.time() < end:
        s = client.get(f"/api/v1/cases/{case_id}/status", headers=h).json()
        if s["status"] in want and not s["running"]:
            return s  # type: ignore[no-any-return]
        time.sleep(1.0)
    raise AssertionError(f"case stayed {s['status']}")


def first_clean_dev_case(prefix: str) -> str:
    index = json.loads((OUTPUT / "index.json").read_text())
    for c in index:
        if c["split"] != "dev" or f"-{prefix}-" not in c["case_id"]:
            continue
        key = json.loads((OUTPUT / "cases" / c["case_id"] / "answer_key.json").read_text())
        if key["expected_stop_stage"] is None and all(
            d["quality"] != "poor" for d in key["documents"]
        ):
            return str(c["case_id"])
    raise LookupError(prefix)


@needs_cases
@pytest.mark.parametrize("prefix", ["PL", "HL", "ED", "BL", "VL"])
def test_one_case_per_loan_type_runs_through_the_api_and_the_officer_confirms(
    client: TestClient, engine: Engine, prefix: str
) -> None:
    case = first_clean_dev_case(prefix)
    h = login(client, "asha")
    case_id = create(client, h, application(case))
    upload_all(client, h, case_id, case)
    assert client.get(f"/api/v1/cases/{case_id}", headers=h).json()["kyc_ready"] is True
    assert client.post(f"/api/v1/cases/{case_id}/submit", headers=h).status_code == 202
    assert client.post(f"/api/v1/cases/{case_id}/submit", headers=h).status_code == 409  # not twice
    wait_for(client, h, case_id, {"awaiting_confirmation"})
    detail = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    rep = detail["report"]
    assert (
        rep["recommendation_text"].startswith("Recommended") and detail["total_score"] is not None
    )
    assert {s["stage"] for s in detail["stages"]} == {
        "extraction",
        "kyc",
        "policy",
        "risk",
        "decision",
    }
    assert any(d["fields"] for d in detail["documents"])
    body = json.dumps(detail)
    for raw in re.findall(r"[A-Z]{5}\d{4}[A-Z]", body):
        raise AssertionError(f"raw PAN in the case view: {raw}")

    # the PDF carries the recommendation and never says "approved"
    pdf = client.get(f"/api/v1/cases/{case_id}/report.pdf", headers=h)
    assert (
        pdf.status_code == 200
        and pdf.content.startswith(b"%PDF")
        and pdf.headers["content-type"] == "application/pdf"
    )
    with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
        words = " ".join(p.get_text() for p in doc)
    # policy clause text may say "approved plan"; the system itself must never claim an approval
    assert "Recommended" in words and not re.search(
        r"\b(is|was|been|are)\s+approved\b", words.lower()
    )

    # confirm: needs the second click
    url = f"/api/v1/cases/{case_id}/confirm"
    assert client.post(url, json={}, headers=h).status_code == 422
    assert client.post(url, json={"second_click": False}, headers=h).status_code == 422
    assert (
        client.get(f"/api/v1/cases/{case_id}/status", headers=h).json()["status"]
        == "awaiting_confirmation"
    )
    done = client.post(url, json={"second_click": True}, headers=h)
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    assert client.post(url, json={"second_click": True}, headers=h).status_code == 409  # once only
    with engine.connect() as c:
        act = c.execute(text("SELECT action, second_click_at FROM officer_actions")).one()
        assert act.action == "confirm" and act.second_click_at is not None
        who = c.execute(
            text(
                "SELECT u.email FROM audit_log l JOIN users u ON u.id = l.actor_id WHERE l.action = 'officer_confirm'"
            )
        ).scalar_one()
        assert who == "asha@example.test"
    timeline = [a["action"] for a in client.get(f"/api/v1/cases/{case_id}/audit", headers=h).json()]
    assert (
        timeline[:3] == ["case_created", "document_uploaded", "document_uploaded"]
        and "officer_confirm" in timeline
    )
    assert "case_submitted" in timeline and "pipeline_finished" in timeline


@needs_cases
def test_override_needs_a_second_click_a_written_reason_and_a_different_decision(
    client: TestClient,
) -> None:
    case = first_clean_dev_case("PL")
    h = login(client, "asha")
    case_id = create(client, h, application(case))
    upload_all(client, h, case_id, case)
    client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    wait_for(client, h, case_id, {"awaiting_confirmation"})
    url = f"/api/v1/cases/{case_id}/override"
    ok_body = {
        "second_click": True,
        "final_decision": "refer",
        "reason": "Income is verified in person at the branch.",
    }
    assert client.post(url, json={**ok_body, "second_click": False}, headers=h).status_code == 422
    assert client.post(url, json={**ok_body, "reason": ""}, headers=h).status_code == 422
    assert client.post(url, json={**ok_body, "reason": "   short  "}, headers=h).status_code == 422
    assert client.post(url, json={**ok_body, "reason": None}, headers=h).status_code == 422
    assert client.post(url, json={**ok_body, "final_decision": None}, headers=h).status_code == 422
    assert (
        client.post(url, json={**ok_body, "final_decision": "approve"}, headers=h).status_code
        == 422
    )  # same as recommended
    assert (
        client.get(f"/api/v1/cases/{case_id}/status", headers=h).json()["status"]
        == "awaiting_confirmation"
    )
    done = client.post(url, json=ok_body, headers=h)
    assert done.status_code == 200 and done.json()["status"] == "overridden"
    detail = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert detail["officer_action"]["final_decision"] == "refer" and detail["officer_action"][
        "reason"
    ].startswith("Income")


@needs_cases
def test_a_fix_type_stop_can_be_resumed_through_the_api(client: TestClient) -> None:
    case = "SYN-PL-D08"  # blurred ID photographs: a correction is needed (EDGE_CASES E-27)
    h = login(client, "asha")
    case_id = create(client, h, application(case))
    upload_all(client, h, case_id, case)
    assert (
        client.post(f"/api/v1/cases/{case_id}/resume", json={}, headers=h).status_code == 409
    )  # not stopped yet
    sub = client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert sub.status_code == 202, sub.text
    wait_for(client, h, case_id, {"stopped"}, seconds=150)
    first = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert (first["stopped_stage"], first["stop_class"]) == ("kyc", "fix") and first[
        "report_version"
    ] == 1
    assert (
        first["total_score"] is None
        and client.post(
            f"/api/v1/cases/{case_id}/confirm", json={"second_click": True}, headers=h
        ).status_code
        == 409
    )
    assert client.post(f"/api/v1/cases/{case_id}/resume", json={}, headers=h).status_code == 202
    wait_for(client, h, case_id, {"stopped"})
    time.sleep(0.5)
    again = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert again["report_version"] == 2  # a correction re-runs the case as a new version
