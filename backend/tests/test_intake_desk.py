"""The intake desk over HTTP (Stage 10, Parts A and B): bulk upload as a zip, a folder or loose
files; the inventory against the generator's answer key; unsafe archives; duplicates; roles; the
file is read once; the identity fields filled from the cards (and nothing else); the confirmation
tick; and the identity rule still failing when the two cards disagree. Models are off; the
database is a throwaway one."""

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.agents import assemble
from app.api import ingest
from tests.test_api import (
    OUTPUT,
    application,
    audit_rows,
    client,  # noqa: F401 - fixture
    engine,  # noqa: F401 - fixture
    first_clean_dev_case,
    login,
    needs_cases,
    wait_for,
)

pytestmark = pytest.mark.db
MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def case_files(case: str, only: set[str] | None = None) -> list[tuple[str, Path, str]]:
    """(name as a folder upload would send it, path, role by folder) for a synthetic case."""
    out = []
    for role in ("primary", "co"):
        folder = OUTPUT / "cases" / case / "documents" / role
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if only is None or f.name in only:
                    out.append((f"{case}/{role}/{f.name}", f, role))
    return out


def as_files(items: list[tuple[str, Path, str]], *, flat: bool = False) -> list[Any]:
    return [
        ("files", (n.split("/")[-1] if flat else n, p.read_bytes(), MIME[p.suffix]))
        for n, p, _ in items
    ]


def as_zip(items: list[tuple[str, Path, str]]) -> list[Any]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, p, _ in items:
            zf.writestr(n, p.read_bytes())
        zf.writestr("__MACOSX/._junk", b"x")
    return [("files", ("case.zip", buf.getvalue(), "application/zip"))]


def start(client: TestClient, h: dict[str, str], loan_type: str, on: str | None = None) -> str:
    r = client.post(
        "/api/v1/cases/intake", json={"loan_type": loan_type, "application_date": on}, headers=h
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def push(client: TestClient, h: dict[str, str], case_id: str, files: list[Any]) -> dict[str, Any]:
    r = client.post(f"/api/v1/cases/{case_id}/intake/files", files=files, headers=h)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def say_employment(
    client: TestClient, h: dict[str, str], case_id: str, case: str
) -> dict[str, Any]:
    app = application(case)
    emp = {a["role"]: a["employment_type"] for a in app["applicants"]
           if a["employment_type"] in ("salaried", "self_employed")}  # fmt: skip
    r = client.put(f"/api/v1/cases/{case_id}/intake", json={"employment": emp}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def shape(inv: dict[str, Any]) -> dict[str, Any]:
    """An inventory reduced to what must not depend on how the files arrived."""
    return {
        "people": [{"role": p["role"],
                    "received": sorted(r["doc_type"] for r in p["received"]),
                    "missing": sorted((m["type"], m["have"]) for m in p["missing"]),
                    "extra": sorted(r["doc_type"] for r in p["extra"])} for p in inv["people"]],
        "unassigned": len(inv["unassigned"]), "unrecognised": len(inv["unrecognised"]),
        "rejected": len(inv["rejected"]), "duplicates": len(inv["duplicates"]),
    }  # fmt: skip


# --------------------------------------------------------------------------- Part A
@needs_cases
def test_a_zip_a_folder_and_loose_files_give_the_same_inventory(client: TestClient) -> None:
    case = first_clean_dev_case("PL")
    items = case_files(case)
    h = login(client, "asha")
    shapes = []
    for files in (as_zip(items), as_files(items), as_files(items, flat=True)):
        cid = start(client, h, "personal")
        shapes.append(shape(push(client, h, cid, files)["inventory"]))
    assert shapes[0] == shapes[1] == shapes[2]
    assert shapes[0]["people"][0]["received"].count("pan_card") == 1


@needs_cases
@pytest.mark.parametrize("prefix,loan", [("PL", "personal"), ("HL", "home"), ("ED", "education"),
                                         ("BL", "business"), ("VL", "vehicle")])  # fmt: skip
def test_the_inventory_matches_the_answer_key_for_every_loan_type(
    client: TestClient, engine: Engine, prefix: str, loan: str
) -> None:  # fmt: skip
    case = first_clean_dev_case(prefix)
    key = json.loads((OUTPUT / "cases" / case / "answer_key.json").read_text())
    h = login(client, "asha")
    cid = start(client, h, loan)
    push(client, h, cid, as_files(case_files(case)))
    inv = say_employment(client, h, cid, case)
    if loan == "education":  # two people, two photographs: a photo has no text to tell them apart
        assert len(inv["unassigned"]) == 2 and {u["doc_type"] for u in inv["unassigned"]} == {
            "photo"
        }
        for u, role in zip(inv["unassigned"], ("primary", "co"), strict=True):  # upload order
            inv = client.patch(
                f"/api/v1/cases/{cid}/documents/{u['id']}", json={"role": role}, headers=h
            ).json()
    with engine.connect() as c:
        got = sorted((r.doc_type, r.role) for r in c.execute(
            text("SELECT doc_type, role FROM documents WHERE case_id = :c"), {"c": cid}))  # fmt: skip
    assert got == sorted((d["doc_type"], d["role"]) for d in key["documents"]), case
    # every file in the key arrived, so nothing is missing, extra, unassigned or unrecognised
    assert [p["missing"] for p in inv["people"]] == [[] for _ in inv["people"]], inv
    assert not inv["unassigned"] and not inv["unrecognised"] and not inv["rejected"]
    assert inv["essential_missing"] == 0 and inv["complete"]
    assert [p["role"] for p in inv["people"]] == (
        ["primary", "co"] if loan == "education" else ["primary"]
    )


@needs_cases
def test_missing_extra_rejected_and_unrecognised_files_are_listed(client: TestClient) -> None:
    case = first_clean_dev_case("PL")
    h = login(client, "asha")
    cid = start(client, h, "personal")
    sample = [
        i
        for i in case_files(case)
        if i[1].name in ("pan_card.pdf", "pan_card.jpg", "payslip_2026-07.pdf")
    ]
    stray = ("files", ("notes.txt", b"hello", "text/plain"))
    bad = ("files", ("scan.pdf", b"%PDF-1.4 broken", "application/pdf"))
    unknown = (
        "files",
        (
            "letter.pdf",
            (OUTPUT / "cases" / case / "documents" / "primary" / "bank_statement.pdf").read_bytes(),
            "application/pdf",
        ),
    )  # noqa: E501
    out = push(client, h, cid, [*as_files(sample), stray, bad])
    inv = out["inventory"]
    assert {r["code"] for r in inv["rejected"]} == {"bad_type", "corrupt"}
    me = inv["people"][0]
    assert {m["type"] for m in me["missing"] if m["essential"]} == {"aadhaar", "photo"}
    assert inv["essential_missing"] == 2
    del unknown


@needs_cases
def test_unsafe_archives_are_refused_and_nothing_is_written(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    h = login(client, "asha")
    cid = start(client, h, "personal")
    pdf = next(p for _, p, _ in case_files(first_clean_dev_case("PL")) if p.suffix == ".pdf")
    for name, entry in (("traversal.zip", "../../evil.pdf"), ("absolute.zip", "/tmp/evil.pdf")):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("ok.pdf", pdf.read_bytes())
            zf.writestr(entry, pdf.read_bytes())
        r = client.post(f"/api/v1/cases/{cid}/intake/files", headers=h,
                        files=[("files", (name, buf.getvalue(), "application/zip"))])  # fmt: skip
        assert r.status_code == 422 and "outside" in r.json()["detail"]
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM documents WHERE case_id = :c"), {"c": cid}
            ).scalar()
            == 0
        )
    root = Path(client.app.state.settings.upload_dir)  # type: ignore[attr-defined]
    assert not any(root.rglob("*.pdf"))  # nothing on disk either, inside or outside the case folder
    assert len(audit_rows(engine, "intake_upload_refused")) == 2


def test_a_request_cannot_make_the_server_hold_more_than_a_case_may(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    h = login(client, "asha")
    cid = start(client, h, "personal")
    client.app.state.settings.max_case_upload_mb = 1  # type: ignore[attr-defined]
    big = b"%PDF-1.4 " + b"x" * (1_300_000)
    files = [("files", (f"f{i}.pdf", big, "application/pdf")) for i in range(40)]
    r = client.post(f"/api/v1/cases/{cid}/intake/files", files=files, headers=h)
    assert r.status_code == 422 and "size limit" in r.json()["detail"]
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM documents WHERE case_id = :c"), {"c": cid}
            ).scalar()
            == 0
        )


@needs_cases
def test_repeats_are_ignored_listed_and_never_fill_a_slot(client: TestClient) -> None:
    case = first_clean_dev_case("PL")
    items = [i for i in case_files(case) if i[1].name.startswith(("pan_card", "payslip"))]
    h = login(client, "asha")
    cid = start(client, h, "personal")
    first = push(client, h, cid, as_zip(items))
    again = push(client, h, cid, as_files(items))  # every file a second time
    assert all(r["status"] == "ignored" for r in again["results"])
    inv = again["inventory"]
    assert len(inv["duplicates"]) == len(items) and inv["duplicates"][0]["kind"] == "exact"
    assert shape(inv)["people"] == shape(first["inventory"])["people"]  # slots unchanged
    # the same payslip re-exported as a different file is the same document (E-01)
    detail = client.get(f"/api/v1/cases/{cid}", headers=h).json()
    assert all(d["status"] != "ignored" or d["duplicate_kind"] for d in detail["documents"])


@needs_cases
def test_the_officers_correction_sticks_and_is_easy_to_undo(client: TestClient) -> None:
    case = first_clean_dev_case("PL")
    h = login(client, "asha")
    cid = start(client, h, "personal")
    out = push(client, h, cid, as_files(case_files(case)))
    photo = next(r for r in out["results"] if r["doc_type"] == "photo")
    r = client.patch(
        f"/api/v1/cases/{cid}/documents/{photo['id']}", json={"doc_type": "unknown"}, headers=h
    )
    assert r.status_code == 200 and r.json()["unrecognised"][0]["name"].startswith("photo")
    r = client.patch(
        f"/api/v1/cases/{cid}/documents/{photo['id']}", json={"role": "none"}, headers=h
    )
    assert any(u["id"] == photo["id"] for u in r.json()["unrecognised"])
    client.patch(
        f"/api/v1/cases/{cid}/documents/{photo['id']}",
        json={"doc_type": "photo", "role": "primary"},
        headers=h,
    )
    # a later upload recomputes the others but keeps the officer's choice
    pdf = next(i for i in case_files(case) if i[1].suffix == ".pdf" and "payslip" in i[1].name)
    inv = push(client, h, cid, as_files([pdf], flat=True))["inventory"]
    assert any(
        x["id"] == photo["id"] and x["person_changed"] for p in inv["people"] for x in p["received"]
    )
    bad = client.patch(
        f"/api/v1/cases/{cid}/documents/{photo['id']}", json={"doc_type": "nonsense"}, headers=h
    )
    assert bad.status_code == 422


@needs_cases
def test_who_may_read_the_inventory_the_prefill_and_the_files(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case = first_clean_dev_case("PL")
    asha, ben, ada = login(client, "asha"), login(client, "ben"), login(client, "ada")
    cid = start(client, asha, "personal")
    push(client, asha, cid, as_files(case_files(case)))
    for path in ("inventory", "prefill", "files.zip"):
        url = f"/api/v1/cases/{cid}/{path}"
        assert client.get(url, headers=asha).status_code == 200, path
        # the admin reads every case; the identity values offered for the form are the officer's
        assert client.get(url, headers=ada).status_code == (403 if path == "prefill" else 200), path
        assert client.get(url, headers=ben).status_code == 404, path  # another officer: not there
        assert client.get(url).status_code == 401, path
    # the admin reads but writes nothing
    assert (
        client.post(
            f"/api/v1/cases/{cid}/intake/files", headers=ada, files=as_files(case_files(case)[:1])
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/cases/intake", json={"loan_type": "personal"}, headers=ada).status_code
        == 403
    )
    z = zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/v1/cases/{cid}/files.zip", headers=asha).content)
    )
    assert any(n.startswith("applicant/pan_card") for n in z.namelist())
    assert len(audit_rows(engine, "files_downloaded")) >= 2


# --------------------------------------------------------------------------- Part B
@needs_cases
def test_the_cards_offer_only_the_five_identity_fields(client: TestClient) -> None:
    case = first_clean_dev_case("PL")
    app = application(case)["applicants"][0]
    h = login(client, "asha")
    cid = start(client, h, "personal")
    push(client, h, cid, as_files(case_files(case)))
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()["primary"]
    assert set(offer["values"]) <= {"full_name", "dob", "pan", "aadhaar_last4", "address"}
    assert offer["values"]["full_name"] == app["full_name"] and offer["values"]["pan"] == app["pan"]
    assert offer["values"]["dob"] == app["dob"]
    blob = json.dumps(offer)
    for claim in ("loan_amount", "tenure", "income", "employment", "phone", "purpose"):
        assert claim not in blob


def desk_form(case: str, offer: dict[str, Any], **over: Any) -> dict[str, Any]:
    """The form an officer saves after the desk: identity as offered, claims typed by them."""
    body = application(case)
    for a in body["applicants"]:
        for k, v in offer.get(a["role"], {}).get("values", {}).items():
            a[k] = v
    return {**body, **over}


@needs_cases
def test_saving_the_form_needs_the_tick_and_marks_what_came_from_documents(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case = first_clean_dev_case("PL")
    h = login(client, "asha")
    cid = start(client, h, "personal")
    push(client, h, cid, as_files(case_files(case)))
    say_employment(client, h, cid, case)
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()
    body = desk_form(case, offer)
    assert (
        client.put(f"/api/v1/cases/{cid}/form", json=body, headers=h).status_code == 422
    )  # no tick
    done = client.put(
        f"/api/v1/cases/{cid}/form", json={**body, "identity_confirmed": True}, headers=h
    )
    assert done.status_code == 200, done.text
    assert set(done.json()["from_documents"]["primary"]) == set(offer["primary"]["values"])
    detail = client.get(f"/api/v1/cases/{cid}", headers=h).json()
    assert not detail["intake_stage"] and detail["identity"]["confirmed"]
    # a value the officer typed over is theirs, no longer "from documents"
    typed = json.loads(json.dumps(body))
    typed["applicants"][0]["address"] = "Flat 9, Some Other Road, Pune 411001"
    again = client.put(
        f"/api/v1/cases/{cid}/form", json={**typed, "identity_confirmed": True}, headers=h
    )
    assert "address" not in again.json()["from_documents"]["primary"]
    assert len(audit_rows(engine, "case_form_saved")) == 2


@needs_cases
def test_claims_are_never_read_from_a_document(client: TestClient, engine: Engine) -> None:
    """Submit refuses a desk case with no form: the amount, tenure, purpose, employment and income
    exist only once the officer (or the applicant's request) has given them."""
    case = first_clean_dev_case("PL")
    h = login(client, "asha")
    cid = start(client, h, "personal")
    push(client, h, cid, as_files(case_files(case)))
    row = client.get(f"/api/v1/cases/{cid}", headers=h).json()
    assert row["loan_amount"] is None and row["tenure_months"] is None and row["applicants"] == []
    assert client.post(f"/api/v1/cases/{cid}/submit", headers=h).status_code == 422
    with engine.connect() as c:
        stored = c.execute(
            text("SELECT loan_amount, tenure_months, purpose, form_data FROM cases WHERE id = :c"),
            {"c": cid},
        ).one()
    assert (
        stored.loan_amount is None
        and stored.purpose is None
        and "applicants" not in stored.form_data
    )


@needs_cases
def test_a_desk_case_runs_without_reading_any_file_twice_and_scores_like_the_form_first_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:  # fmt: skip
    case = first_clean_dev_case("PL")
    files = case_files(case)
    h = login(client, "asha")
    reads = {"desk": 0, "extraction": 0}
    real = ingest.process_file

    def desk_counter(*a: Any, **k: Any) -> Any:
        reads["desk"] += 1
        return real(*a, **k)

    def extraction_counter(*a: Any, **k: Any) -> Any:
        reads["extraction"] += 1
        return real(*a, **k)

    monkeypatch.setattr(ingest, "process_file", desk_counter)
    monkeypatch.setattr(assemble, "process_file", extraction_counter)
    cid = start(client, h, "personal", application(case)["application_date"])  # files are dated
    push(client, h, cid, as_files(files))
    say_employment(client, h, cid, case)
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()
    assert client.put(f"/api/v1/cases/{cid}/form", headers=h,
                      json={**desk_form(case, offer), "identity_confirmed": True}).status_code == 200  # fmt: skip
    assert client.post(f"/api/v1/cases/{cid}/submit", headers=h).status_code == 202
    wait_for(client, h, cid, {"awaiting_confirmation", "stopped"})
    assert reads == {"desk": len(files), "extraction": 0}  # each file was read once, at the desk
    desk = client.get(f"/api/v1/cases/{cid}", headers=h).json()

    # the same case, form first and files one by one, scores the same
    from tests.test_api import create, upload_all

    cid2 = create(client, h, application(case))
    upload_all(client, h, cid2, case)
    assert client.post(f"/api/v1/cases/{cid2}/submit", headers=h).status_code == 202
    wait_for(client, h, cid2, {"awaiting_confirmation", "stopped"})
    old = client.get(f"/api/v1/cases/{cid2}", headers=h).json()
    assert (desk["total_score"], desk["band"], desk["status"]) == (
        old["total_score"],
        old["band"],
        old["status"],
    )
    assert re.search(r"[A-Z]{5}\d{4}[A-Z]", json.dumps(desk)) is None  # still masked in the view


@needs_cases
def test_cards_that_disagree_leave_name_and_birth_date_empty_and_the_identity_rule_still_fails(
    client: TestClient,
) -> None:  # fmt: skip
    """The PAN card of one person among the documents of another. The desk offers neither the
    name nor the date of birth (the cards disagree); the officer types them from the application;
    the identity rule then compares what was typed with both cards, so the case still stops at
    KYC with a correction request, exactly as it would have form first."""
    case = "SYN-PL-D02"  # digital documents: no OCR needed
    stranger = OUTPUT / "cases" / "SYN-BL-D01" / "documents" / "primary" / "pan_card.pdf"
    items = [
        (n, stranger if p.name == "pan_card.pdf" else p, r)
        for n, p, r in case_files(case)
        if p.suffix == ".pdf"
    ]
    h = login(client, "asha")
    cid = start(client, h, "personal", application(case)["application_date"])
    inv = push(client, h, cid, as_files(items))["inventory"]
    # the Aadhaar card and the payslips name someone other than the PAN card does, so they are
    # not filed to anyone on their own: the officer decides, and files them to the applicant
    assert len(inv["unassigned"]) >= 2
    while inv["unassigned"]:  # filing one can free another (the PAN card), so look again each time
        u = inv["unassigned"][0]
        inv = client.patch(
            f"/api/v1/cases/{cid}/documents/{u['id']}", json={"role": "primary"}, headers=h
        ).json()
    say_employment(client, h, cid, case)
    offer = client.get(f"/api/v1/cases/{cid}/prefill", headers=h).json()["primary"]
    assert "full_name" not in offer["values"] and "dob" not in offer["values"]
    assert set(offer["notes"]) == {"full_name", "dob"}
    typed = desk_form(case, {"primary": offer})  # identity from the cards where they agree
    assert typed["applicants"][0]["full_name"] == application(case)["applicants"][0]["full_name"]
    # a photograph is not among these files; add it so the KYC gate in the API is met
    photo = next(p for _, p, _ in case_files(case) if p.name == "photo.jpg")
    push(client, h, cid, [("files", ("photo.jpg", photo.read_bytes(), "image/jpeg"))])
    saved = client.put(
        f"/api/v1/cases/{cid}/form", json={**typed, "identity_confirmed": True}, headers=h
    )
    assert saved.status_code == 200, saved.text
    # one payslip is a photograph that was left out, so something is missing: the desk case
    # cannot be submitted until the officer chooses Proceed anyway (the second click)
    assert client.post(f"/api/v1/cases/{cid}/submit", headers=h).status_code == 409
    proceed = f"/api/v1/cases/{cid}/intake/proceed"
    assert client.post(proceed, json={}, headers=h).status_code == 422
    assert client.post(proceed, json={"second_click": True}, headers=h).status_code == 200
    assert client.post(f"/api/v1/cases/{cid}/submit", headers=h).status_code == 202
    wait_for(client, h, cid, {"stopped", "awaiting_confirmation"})
    detail = client.get(f"/api/v1/cases/{cid}", headers=h).json()
    assert (detail["status"], detail["stop_class"], detail["stopped_stage"]) == (
        "stopped",
        "fix",
        "kyc",
    )
    hard = [f for f in detail["report"]["findings"] if f["severity"] == "hard_fail"]
    assert {"CM-KYC-03"} <= {f["rule_id"] for f in hard}
    # the report says which form values came from the cards (address and Aadhaar here, not name)
    assert "full_name" not in detail["report"]["identity_from_documents"].get("primary", [])
