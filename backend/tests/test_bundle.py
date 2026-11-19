"""Several documents in one PDF (Stage 10, Part D): the page-level split on synthetic bundles, the
officer's edit, the second click, pieces linked to the original, the bundle limits, the switch and
the gates. Models are off; the HTTP tests use a throwaway database."""

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.intake import bundle, upload
from app.intake.evaluate_bundles import build_bundle
from app.intake.models import DocType
from app.intake.reader import read_document
from tests.test_api import (
    OUTPUT,
    client,  # noqa: F401 - fixture
    engine,  # noqa: F401 - fixture
    login,
    needs_cases,
)
from tests.test_intake_desk import case_files, push, say_employment, shape, start

ALL_TYPES = {t.value for t in DocType}


def digital_docs(case: str) -> list[dict[str, Any]]:
    key = json.loads((OUTPUT / "cases" / case / "answer_key.json").read_text())
    return [
        d for d in key["documents"] if d["format"] == "digital_pdf" and d["doc_type"] != "photo"
    ]


def pick_case(prefix: str, minimum: int = 3) -> str:
    """The first dev case of this loan type with at least `minimum` text-layer documents, all the
    primary applicant's (so the stack and the loose files describe one person)."""
    for c in json.loads((OUTPUT / "index.json").read_text()):
        if c["split"] != "dev" or f"-{prefix}-" not in c["case_id"]:
            continue
        docs = digital_docs(c["case_id"])
        if len(docs) >= minimum and all(d["role"] == "primary" for d in docs):
            return str(c["case_id"])
    raise LookupError(prefix)


def stack(case: str) -> tuple[bytes, list[str], list[tuple[int, int, str]]]:
    """One PDF made of the case's text-layer documents, the true type of each page and the true
    (first page, last page, type) of each document."""
    key = json.loads((OUTPUT / "cases" / case / "answer_key.json").read_text())
    return build_bundle(OUTPUT / "cases" / case, key, "digital")


def loose(case: str) -> list[Any]:
    """The same documents as separate files, the way the desk's upload sends them."""
    names = {Path(d["file"]).name for d in digital_docs(case)}
    return [
        ("files", (n.split("/")[-1], p.read_bytes(), "application/pdf"))
        for n, p, _ in case_files(case, names)
    ]


def read_pages(data: bytes) -> Any:
    chk = upload.check_upload(data, "b.pdf", 10**9, bundle_pages=500)
    assert chk.accepted, chk.message
    return read_document(data, chk).pages


def text_page_pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Continuation sheet {i} of a long document " * 2)
    data = bytes(doc.tobytes())
    doc.close()
    return data


def as_tuples(segments: list[bundle.Segment]) -> list[tuple[int, int, str]]:
    return [(s.page_from, s.page_to, s.doc_type) for s in segments]


# --------------------------------------------------------------------------- the split itself
@needs_cases
@pytest.mark.parametrize("prefix", ["PL", "HL", "BL", "ED", "VL"])
def test_a_stack_of_a_whole_case_is_split_at_every_title(prefix: str) -> None:
    data, truth_pages, truth_docs = stack(pick_case(prefix))
    segments = bundle.propose(read_pages(data))
    assert bundle.page_accuracy(truth_pages, segments) == (len(truth_pages),) * 2
    assert as_tuples(segments) == truth_docs  # a multi-page statement stays whole
    assert bundle.is_bundle(segments)


@needs_cases
def test_one_multi_page_statement_is_not_a_bundle() -> None:
    root = OUTPUT / "cases"
    paths = [
        p
        for p in sorted(root.glob("*/documents/primary/bank_statement.pdf"))
        if pymupdf.open(p).page_count >= 3
    ]
    assert paths
    segments = bundle.propose(read_pages(paths[0].read_bytes()))
    assert [s.doc_type for s in segments] == ["bank_statement"] and len(segments) == 1
    assert not bundle.is_bundle(segments)


def test_a_page_without_a_title_continues_the_document_before_it() -> None:
    segments = bundle.propose(read_pages(text_page_pdf(3)))  # three untitled pages
    assert as_tuples(segments) == [(1, 3, "unknown")]  # the first page is unrecognised, not guessed


@needs_cases
def test_an_unrecognised_first_page_is_its_own_unrecognised_document() -> None:
    data, _, docs = stack(pick_case("PL"))
    out = pymupdf.open(stream=text_page_pdf(1))
    out.insert_pdf(pymupdf.open(stream=data))
    segments = bundle.propose(read_pages(bytes(out.tobytes())))
    assert as_tuples(segments)[:2] == [(1, 1, "unknown"), (2, docs[0][1] + 1, docs[0][2])]


@needs_cases
def test_two_payslips_in_a_row_are_two_documents() -> None:
    case = pick_case("PL")
    key = json.loads((OUTPUT / "cases" / case / "answer_key.json").read_text())
    slips = [
        d for d in key["documents"] if d["doc_type"] == "payslip" and d["format"] == "digital_pdf"
    ]
    if len(slips) < 2:
        pytest.skip("no case with two text-layer payslips")
    out = pymupdf.open()
    for d in slips:
        out.insert_pdf(pymupdf.open(OUTPUT / "cases" / case / d["file"]))
    assert len(bundle.propose(read_pages(bytes(out.tobytes())))) == len(slips)


# --------------------------------------------------------------------------- the officer's edit
def test_a_split_must_cover_every_page_once_in_order() -> None:
    ok = [
        {"page_from": 1, "page_to": 2, "doc_type": "pan_card"},
        {"page_from": 3, "page_to": 5, "doc_type": "bank_statement"},
    ]
    assert as_tuples(bundle.validate(ok, 5, ALL_TYPES)) == [
        (1, 2, "pan_card"),
        (3, 5, "bank_statement"),
    ]
    one = {"page_from": 1, "page_to": 5, "doc_type": "pan_card"}
    for bad, why in (
        ([], "at least one"),
        ([{**one, "page_from": 2}], "gap"),
        ([{**one, "page_to": 3}, {**one, "page_from": 3, "doc_type": "aadhaar"}], "overlap"),
        ([{**one, "page_to": 4}], "do not"),
        ([{**one, "page_to": 9}], "not inside"),
        ([{**one, "doc_type": "passport"}], "Unknown document type"),
        ([{**one, "page_from": 3, "page_to": 2}], "gap"),
        ([{**one, "page_from": "x"}], "needs a first page"),
    ):
        with pytest.raises(bundle.SplitError, match=why):
            bundle.validate(bad, 5, ALL_TYPES)


@needs_cases
def test_cutting_leaves_the_original_alone_and_a_whole_cut_is_the_original() -> None:
    data, truth, _ = stack(pick_case("PL"))
    before = bytes(data)
    piece = bundle.cut(data, bundle.Segment(2, 3, "aadhaar"))
    assert pymupdf.open(stream=piece).page_count == 2 and data == before
    assert bundle.cut(data, bundle.Segment(1, len(truth), "unknown")) is data


# --------------------------------------------------------------------------- the bundle limits
def test_a_bundle_may_have_more_pages_than_one_document() -> None:
    data = text_page_pdf(upload.MAX_PAGES + 5)
    assert upload.check_upload(data, "x.pdf", 10**8).reject_code == "too_many_pages"
    assert upload.check_upload(data, "x.pdf", 10**8, bundle_pages=120).accepted
    assert (
        upload.check_upload(data, "x.pdf", 10**8, bundle_pages=20).reject_code == "too_many_pages"
    )


def test_every_scanned_page_is_checked_for_blur_and_the_bad_page_is_named() -> None:
    def scan(blurred: bool) -> bytes:
        img = np.full((1100, 800, 3), 255, np.uint8)
        for y in range(80, 1000, 45):
            cv2.putText(img, "Statement of account 12345 ABCDE", (40, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)  # fmt: skip
        if blurred:
            img = cv2.GaussianBlur(img, (0, 0), 14)
        return bytes(cv2.imencode(".jpg", img)[1])

    doc = pymupdf.open()
    for i in range(6):  # the sixth page is the blurred one: a sample of three would miss it
        page = doc.new_page(width=595, height=820)
        page.insert_image(page.rect, stream=scan(blurred=i == 5))
    data = bytes(doc.tobytes())
    sampled = upload.check_upload(data, "x.pdf", 10**8)
    every = upload.check_upload(data, "x.pdf", 10**8, bundle_pages=50)
    assert sampled.accepted
    assert every.reject_code == "blurry" and "Page 6" in every.message


# --------------------------------------------------------------------------- over HTTP
def upload_bundle(client: TestClient, h: dict[str, str], cid: str, data: bytes,
                  name: str = "all-my-documents.pdf") -> dict[str, Any]:  # fmt: skip
    return push(client, h, cid, [("files", (name, data, "application/pdf"))])


def stored(engine: Engine, cid: str) -> list[Any]:
    with engine.connect() as c:
        return list(c.execute(
            text("""SELECT id, doc_type, status, original_name, parent_document_id, page_from,
                           page_to, role, type_source, classification, file_path
                    FROM documents WHERE case_id = :c ORDER BY uploaded_at, original_name"""),
            {"c": cid}))  # fmt: skip


@needs_cases
def test_a_bundle_waits_for_the_officer_and_blocks_going_on_until_it_is_split(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    data, _, docs = stack(pick_case("PL"))
    h = login(client, "asha")
    cid = start(client, h, "personal")
    out = upload_bundle(client, h, cid, data)
    assert [r["status"] for r in out["results"]] == ["bundle"]
    inv = out["inventory"]
    (b,) = inv["bundles"]
    assert [(s["page_from"], s["page_to"], s["doc_type"]) for s in b["segments"]] == docs
    assert b["segments"] == b["proposed"] and inv["counts"]["bundles"] == 1
    assert inv["counts"]["received"] == 0 and not inv["complete"]
    row = next(r for r in stored(engine, cid) if r.status == "bundle")
    assert Path(row.file_path).read_bytes() == data  # the original, untouched
    assert "bundle_uploaded" in client.get(f"/api/v1/cases/{cid}/audit", headers=h).text
    r = client.post(f"/api/v1/cases/{cid}/intake/proceed", json={"second_click": True}, headers=h)
    assert r.status_code == 409 and "split" in r.json()["detail"]


@needs_cases
def test_confirming_the_split_files_each_piece_like_a_file_of_its_own(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    case = pick_case("PL")
    data, _, docs = stack(case)
    h = login(client, "asha")
    # the same documents sent as separate files: the inventory the stack must end up with
    other = start(client, h, "personal")
    push(client, h, other, loose(case))
    want = shape(say_employment(client, h, other, case))

    cid = start(client, h, "personal")
    b = upload_bundle(client, h, cid, data)["inventory"]["bundles"][0]
    url = f"/api/v1/cases/{cid}/documents/{b['id']}/split/confirm"
    assert client.post(url, json={}, headers=h).status_code == 422  # no second click, no cut
    assert client.post(url, json={"second_click": False}, headers=h).status_code == 422
    assert not [r for r in stored(engine, cid) if r.parent_document_id]

    res = client.post(url, json={"second_click": True}, headers=h)
    assert res.status_code == 200, res.text
    say_employment(client, h, cid, case)
    inv = client.get(f"/api/v1/cases/{cid}/inventory", headers=h).json()
    assert shape(inv) == want and not inv["bundles"]
    assert [x["pieces"] for x in inv["splits"]] == [len(docs)]

    rows = stored(engine, cid)
    original = next(r for r in rows if r.status == "split")
    pieces = [r for r in rows if r.parent_document_id]
    assert len(pieces) == len(docs) and all(r.parent_document_id == original.id for r in pieces)
    assert all(r.status == "accepted" and r.role == "primary" for r in pieces)
    assert sorted((r.page_from, r.page_to) for r in pieces) == [(a, z) for a, z, _ in docs]
    assert Path(original.file_path).read_bytes() == data  # still untouched
    # each piece has its own file and its own saved read (so Extraction reads nothing again)
    for r in pieces:
        assert Path(r.file_path).is_file() and Path(r.file_path + ".read.json").is_file()
    assert "bundle_split_confirmed" in client.get(f"/api/v1/cases/{cid}/audit", headers=h).text


@needs_cases
def test_the_officer_can_merge_and_relabel_before_confirming(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    data, truth, _ = stack(pick_case("PL"))
    h = login(client, "asha")
    cid = start(client, h, "personal")
    b = upload_bundle(client, h, cid, data)["inventory"]["bundles"][0]
    n = b["pages"]
    assert n == len(truth)
    put = f"/api/v1/cases/{cid}/documents/{b['id']}/split"
    for bad in (
        [],
        [{"page_from": 1, "page_to": n - 1, "doc_type": "pan_card"}],
        [{"page_from": 1, "page_to": n, "doc_type": "passport"}],
    ):
        assert client.put(put, json={"segments": bad}, headers=h).status_code == 422
    one = {"page_from": 1, "page_to": n, "doc_type": "bank_statement"}  # "it is one document"
    saved = client.put(put, json={"segments": [one]}, headers=h)
    assert saved.status_code == 200
    (shown,) = saved.json()["bundles"]
    assert len(shown["segments"]) == 1 and shown["segments"] != shown["proposed"]
    done = client.post(f"/api/v1/cases/{cid}/documents/{b['id']}/split/confirm",
                       json={"second_click": True}, headers=h)  # fmt: skip
    assert done.status_code == 200, done.text
    (piece,) = [r for r in stored(engine, cid) if r.parent_document_id]
    assert piece.status == "accepted" and (piece.page_from, piece.page_to) == (1, n)
    assert piece.doc_type == "bank_statement" and piece.type_source == "officer"
    assert piece.classification in ALL_TYPES and piece.classification != "bank_statement"


@needs_cases
def test_the_same_bundle_twice_is_ignored_and_a_piece_that_repeats_a_file_is_too(
    client: TestClient,
) -> None:  # fmt: skip
    case = pick_case("PL")
    data, _, _ = stack(case)
    h = login(client, "asha")
    cid = start(client, h, "personal")
    upload_bundle(client, h, cid, data)
    again = upload_bundle(client, h, cid, data, name="copy.pdf")
    assert [r["status"] for r in again["results"]] == ["ignored"]
    # a loose file that one piece repeats: after the split it is filed once, not twice
    pan = next(d for d in digital_docs(case) if d["doc_type"] == "pan_card")
    pan_bytes = (OUTPUT / "cases" / case / pan["file"]).read_bytes()
    push(client, h, cid, [("files", ("pan.pdf", pan_bytes, "application/pdf"))])
    inv = client.get(f"/api/v1/cases/{cid}/inventory", headers=h).json()
    res = client.post(f"/api/v1/cases/{cid}/documents/{inv['bundles'][0]['id']}/split/confirm",
                      json={"second_click": True}, headers=h).json()  # fmt: skip
    assert sum(r["status"] == "ignored" for r in res["results"]) == 1
    cards = [
        r for p in res["inventory"]["people"] for r in p["received"] if r["doc_type"] == "pan_card"
    ]
    assert len(cards) == 1


@needs_cases
def test_with_the_switch_off_a_multi_page_pdf_is_one_document(client: TestClient) -> None:
    data, _, _ = stack(pick_case("PL"))
    h = login(client, "asha")
    client.app.state.settings.bundle_split_enabled = False  # type: ignore[attr-defined]
    cid = start(client, h, "personal")
    out = upload_bundle(client, h, cid, data)
    assert [r["status"] for r in out["results"]] == ["accepted"]
    assert out["inventory"]["bundles"] == [] and out["inventory"]["counts"]["bundles"] == 0


@needs_cases
def test_only_the_owning_officer_edits_a_split(client: TestClient) -> None:
    data, _, _ = stack(pick_case("PL"))
    asha, ben, ada = login(client, "asha"), login(client, "ben"), login(client, "ada")
    cid = start(client, asha, "personal")
    b = upload_bundle(client, asha, cid, data)["inventory"]["bundles"][0]
    base = f"/api/v1/cases/{cid}/documents/{b['id']}/split"
    body = {"segments": [{"page_from": 1, "page_to": b["pages"], "doc_type": "unknown"}]}
    assert client.put(base, json=body, headers=ben).status_code == 404  # another officer's case
    assert client.put(base, json=body, headers=ada).status_code == 403  # admin reads, never writes
    ok = {"second_click": True}
    assert client.post(base + "/confirm", json=ok, headers=ada).status_code == 403
    assert client.put(base, json=body).status_code == 401
    assert client.get(f"/api/v1/cases/{cid}/inventory", headers=ada).json()["bundles"]


@needs_cases
def test_single_documents_do_not_become_bundles(client: TestClient) -> None:
    case = pick_case("PL")
    by_type = {d["doc_type"]: d for d in digital_docs(case)}
    h = login(client, "asha")
    cid = start(client, h, "personal")
    files = [
        (
            "files",
            (f"{kind}.pdf", (OUTPUT / "cases" / case / d["file"]).read_bytes(), "application/pdf"),
        )
        for kind, d in by_type.items()
        if pymupdf.open(OUTPUT / "cases" / case / d["file"]).page_count >= 1
    ]
    out = push(client, h, cid, files)
    assert {r["status"] for r in out["results"]} == {"accepted"}
    assert out["inventory"]["bundles"] == []
