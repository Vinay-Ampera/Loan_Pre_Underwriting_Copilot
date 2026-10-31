"""Stage 4: index, retrieval filters, precedents, grounding and the evaluation set.

DB tests use a throwaway database. Embeddings and rerank are faked (tests/rag_helpers.py) so no
model is loaded; the real models are exercised by `python -m app.rag.evaluate`.
"""

import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from alembic import command
from sqlalchemy import Connection, create_engine, text

from app.core.config import REPO_ROOT
from app.db.migrate import alembic_config
from app.rag.evaluate import (
    BASELINE_PATH,
    Query,
    check_targets,
    citation_validity,
    load_queries,
    score_query,
)
from app.rag.grounding import check_grounding
from app.rag.index import reindex
from app.rag.policy_loader import POLICY_DIR, load_all
from app.rag.precedents import find_precedents, precedent_text
from app.rag.retrieve import PolicyRetriever, merge
from app.rag.schemas import FitFindingLLM, RetrievedClause
from app.scoring.rules import RuleSet, load_rules
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return load_rules()


@pytest.fixture
def conn(clean_db_url: str) -> Iterator[Connection]:
    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)
    with engine.connect() as c:
        yield c
    engine.dispose()


@pytest.fixture
def policy_copy(tmp_path: Path) -> Path:
    for p in POLICY_DIR.glob("*.md"):
        shutil.copy(p, tmp_path / p.name)
    return tmp_path


def retriever(conn: Connection) -> PolicyRetriever:
    return PolicyRetriever(conn, embed=fake_vector, rerank_fn=fake_rerank)


def chunk_count(conn: Connection, active_only: bool = True) -> int:
    where = "WHERE d.active" if active_only else ""
    return conn.execute(
        text(
            "SELECT count(*) FROM policy_chunks c JOIN policy_documents d "
            f"ON d.id = c.policy_document_id {where}"
        )
    ).scalar_one()


# --- re-index --------------------------------------------------------------------------------
@pytest.mark.db
def test_reindex_embeds_every_clause_then_is_a_no_op(conn: Connection) -> None:
    total = sum(len(d.clauses) for d in load_all())
    first = reindex(conn, embed=fake_embed_passages)
    assert first.embedded == total and first.touched
    missing = conn.execute(text("SELECT count(*) FROM policy_chunks WHERE embedding IS NULL"))
    assert missing.scalar_one() == 0

    second = reindex(conn, embed=fake_embed_passages)
    assert second.embedded == 0 and not second.touched
    assert chunk_count(conn) == total


@pytest.mark.db
def test_reindex_picks_up_an_edited_clause(conn: Connection, policy_copy: Path) -> None:
    reindex(conn, docs=load_all(policy_copy), embed=fake_embed_passages)
    home = policy_copy / "home.md"
    home.write_text(
        home.read_text().replace("A credit score of 700 or above", "A credit score of 720 or above")
    )
    report = reindex(conn, docs=load_all(policy_copy), embed=fake_embed_passages)
    changed = {c for d in report.docs for c in d.changed}
    assert changed == {"HL-ELIG-03"} and report.embedded == 1
    stored = conn.execute(text("SELECT text FROM policy_chunks WHERE clause_id = 'HL-ELIG-03'"))
    assert "720" in stored.scalar_one()


@pytest.mark.db
def test_reindex_new_version_becomes_active_and_removed_clause_is_deleted(
    conn: Connection, policy_copy: Path
) -> None:
    reindex(conn, docs=load_all(policy_copy), embed=fake_embed_passages)
    vehicle = policy_copy / "vehicle.md"
    raw = vehicle.read_text().replace("2026.10.31-1", "2026.11.15-1")
    vehicle.write_text(
        raw.split("## VL-STAB-01")[0] + "## VL-PROD-01" + raw.split("## VL-PROD-01")[1]
    )
    report = reindex(conn, docs=load_all(policy_copy), embed=fake_embed_passages)
    v = next(d for d in report.docs if d.loan_type == "vehicle")
    assert v.new_version and "VL-STAB-01" not in v.added
    versions = conn.execute(
        text("SELECT version, active FROM policy_documents WHERE loan_type = 'vehicle' ORDER BY 1")
    ).all()
    assert [(r.version, r.active) for r in versions] == [
        ("2026.10.31-1", False),
        ("2026.11.15-1", True),
    ]
    body = next(
        c.text for d in load_all(policy_copy) for c in d.clauses if c.clause_id == "VL-PROD-01"
    )
    hits = retriever(conn).search(body, "vehicle", top_k=20, rerank=False)
    assert {h.doc_version for h in hits if h.doc_loan_type == "vehicle"} == {"2026.11.15-1"}
    assert "VL-STAB-01" not in {h.clause_id for h in hits}


@pytest.mark.db
def test_reindex_writes_an_audit_row(conn: Connection) -> None:
    reindex(conn, embed=fake_embed_passages)
    row = conn.execute(text("SELECT after FROM audit_log WHERE action = 'policy_reindex'")).one()
    assert row.after["embedded"] > 0


# --- retrieval filters -----------------------------------------------------------------------
@pytest.mark.db
def test_search_filters_by_loan_type_and_active_version(conn: Connection) -> None:
    reindex(conn, embed=fake_embed_passages)
    r = retriever(conn)
    for loan, prefix in [("home", "HL-"), ("vehicle", "VL-"), ("personal", "PL-")]:
        hits = r.search("credit score minimum tenure income", loan, top_k=30, rerank=False)
        assert hits
        assert all(h.clause_id.startswith(("CM-", prefix)) for h in hits), loan
        assert all(h.active for h in hits)
    conn.execute(text("UPDATE policy_documents SET active = false WHERE loan_type = 'home'"))
    hits = r.search("home loan credit score", "home", top_k=30, rerank=False)
    assert hits and all(h.clause_id.startswith("CM-") for h in hits)


@pytest.mark.db
def test_rerank_orders_by_relevance_and_by_ids_marks_rule_links(conn: Connection) -> None:
    reindex(conn, embed=fake_embed_passages)
    r = retriever(conn)
    hits = r.search("bounced cheques and NACH returns", "personal", top_k=5)
    assert hits[0].clause_id == "CM-CRD-02"
    assert [h.relevance for h in hits] == sorted((h.relevance for h in hits), reverse=True)
    linked = r.by_ids(["HL-PROD-02", "PL-PROD-02"], "home")  # PL clause is the wrong loan type
    assert [c.clause_id for c in linked] == ["HL-PROD-02"] and linked[0].via == "rule"


def clause(cid: str, rel: float, via: str = "search", loan: str = "common") -> RetrievedClause:
    return RetrievedClause(
        clause_id=cid, title="t", text=f"text of {cid}", source_tag="sample", doc_loan_type=loan,
        doc_version="v1", relevance=rel, via=via,  # type: ignore[arg-type]
    )  # fmt: skip


def test_merge_keeps_best_relevance_and_prefers_rule_links() -> None:
    merged = merge([clause("A", 0.4), clause("B", 0.9)], [clause("A", 1.0, "rule")])
    assert [(c.clause_id, c.via) for c in merged] == [("A", "rule"), ("B", "search")]


# --- precedents ------------------------------------------------------------------------------
def add_precedent(conn: Connection, **over: object) -> str:
    uid = conn.execute(
        text(
            "INSERT INTO users (name, email, password_hash, role) "
            "VALUES ('t', :e, 'x', 'admin') RETURNING id"
        ),
        {"e": f"{uuid.uuid4().hex[:8]}@example.test"},
    ).scalar_one()
    case_id = conn.execute(
        text(
            "INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months) "
            "VALUES (:n, 'personal', :u, 100000, 12) RETURNING id"
        ),
        {"n": f"CASE-2026-{uuid.uuid4().int % 10000:04d}", "u": uid},
    ).scalar_one()
    row = {
        "status": "approved", "loan_type": "personal", "valid_until": date.today() + timedelta(days=30),
        "rules": ["PL-ELIG-04"], "band": "refer", **over,
    }  # fmt: skip
    vec = fake_vector(precedent_text(str(row["loan_type"]), list(row["rules"]), "refer"))  # type: ignore[call-overload]
    return str(
        conn.execute(
            text(
                """INSERT INTO precedents (source_case_id, status, loan_type, rule_ids,
                       original_recommendation, final_decision, officer_reason, report_summary,
                       embedding, proposed_by, reviewed_by, reviewed_at, valid_until)
                   VALUES (:c, :s, :lt, :r, 'refer', 'approve', 'income verified by visit',
                       'Salary slightly under minimum; officer verified extra income.',
                       CAST(:e AS vector), :u, :u, now(), :v) RETURNING id"""
            ),
            {
                "c": case_id,
                "s": row["status"],
                "lt": row["loan_type"],
                "r": row["rules"],
                "e": str(vec),
                "u": uid,
                "v": row["valid_until"],
            },
        ).scalar_one()  # fmt: skip
    )


def precedents_for(
    conn: Connection, ruleset: RuleSet, monkeypatch: pytest.MonkeyPatch, **over: object
) -> list[str]:
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)
    args: dict[str, object] = {
        "loan_type": "personal", "band": "refer", "rule_ids": ["PL-ELIG-04"], "hard_failed": False,
        **over,
    }  # fmt: skip
    return [m.id for m in find_precedents(conn, ruleset=ruleset, **args)]  # type: ignore[arg-type]


@pytest.mark.db
def test_precedent_is_found_for_a_similar_refer_case(
    conn: Connection, ruleset: RuleSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = add_precedent(conn)
    assert precedents_for(conn, ruleset, monkeypatch) == [pid]


@pytest.mark.db
def test_precedent_is_skipped_when_not_allowed(
    conn: Connection, ruleset: RuleSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_precedent(conn)
    assert precedents_for(conn, ruleset, monkeypatch, band="approve") == []
    assert precedents_for(conn, ruleset, monkeypatch, band="reject") == []
    assert precedents_for(conn, ruleset, monkeypatch, hard_failed=True) == []
    assert precedents_for(conn, ruleset, monkeypatch, loan_type="home") == []
    assert precedents_for(conn, ruleset, monkeypatch, rule_ids=["BL-STAB-02", "CM-CRD-04"]) == []


@pytest.mark.db
def test_precedent_pending_expired_or_held_is_never_used(
    conn: Connection, ruleset: RuleSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_precedent(conn, valid_until=date.today() - timedelta(days=1))
    add_precedent(conn, status="expired")
    for status in ("pending", "held", "rejected"):
        add_precedent(conn, status=status)
    assert precedents_for(conn, ruleset, monkeypatch) == []


# --- grounding -------------------------------------------------------------------------------
def finding(**over: object) -> FitFindingLLM:
    base: dict[str, object] = {
        "rule_id": "HL-CIBIL-01", "clause_ids": ["HL-ELIG-03"], "assessment": "concern",
        "statement": "Score is below the floor.", "quote": "A credit score of 700 or above",
    }  # fmt: skip
    return FitFindingLLM(**{**base, **over})  # type: ignore[arg-type]


def retrieved_home() -> list[RetrievedClause]:
    text_ = next(c.text for d in load_all() for c in d.clauses if c.clause_id == "HL-ELIG-03")
    return [
        RetrievedClause(clause_id="HL-ELIG-03", title="Credit score", text=text_,
                        source_tag="public", doc_loan_type="home", doc_version="v1", relevance=0.9),
        RetrievedClause(clause_id="PL-ELIG-03", title="Credit score", text="personal text",
                        source_tag="public", doc_loan_type="personal", doc_version="v1", relevance=0.9),
        RetrievedClause(clause_id="CM-CRD-04", title="Enquiries", text="Many credit enquiries",
                        source_tag="sample", doc_loan_type="common", doc_version="v1", relevance=0.05),
        RetrievedClause(clause_id="CM-CRD-01", title="Bureau", text="bureau score text",
                        source_tag="public", doc_loan_type="common", doc_version="v1", relevance=0.7,
                        active=False),
    ]  # fmt: skip


def codes(findings: list[FitFindingLLM], ruleset: RuleSet) -> set[str]:
    rep = check_grounding(findings, retrieved_home(), "home", ruleset, min_relevance=0.1)
    return {i.code for i in rep.issues}


def test_grounded_finding_passes(ruleset: RuleSet) -> None:
    assert codes([finding()], ruleset) == set()


def test_a_clause_that_was_not_retrieved_is_caught(ruleset: RuleSet) -> None:
    assert codes([finding(clause_ids=["HL-ELIG-03", "HL-PROD-99"])], ruleset) == {"not_retrieved"}


def test_every_grounding_failure_class_is_detected(ruleset: RuleSet) -> None:
    assert codes([finding(clause_ids=[])], ruleset) == {"no_citation"}
    assert codes([finding(clause_ids=["PL-ELIG-03"], quote="personal text")], ruleset) == {
        "wrong_loan_type"
    }
    assert codes([finding(clause_ids=["CM-CRD-04"], quote="Many credit enquiries")], ruleset) == {
        "low_relevance"
    }
    assert codes([finding(clause_ids=["CM-CRD-01"], quote="bureau score")], ruleset) == {
        "inactive_version"
    }
    assert codes([finding(quote="the applicant is wealthy")], ruleset) == {"unsupported_quote"}
    assert codes([finding(rule_id="XX-FAKE-01")], ruleset) == {"unknown_rule"}
    assert codes([finding(rule_id="PL-CIBIL-01")], ruleset) == {"unknown_rule"}  # not a home rule


def test_quote_match_ignores_case_and_punctuation(ruleset: RuleSet) -> None:
    assert codes([finding(quote="a CREDIT score, of 700 or above!")], ruleset) == set()


# --- evaluation set --------------------------------------------------------------------------
def test_eval_set_is_well_formed() -> None:
    raw = yaml.safe_load((REPO_ROOT / "data" / "rag" / "retrieval_eval.yaml").read_text())[
        "queries"
    ]
    ids = [q["id"] for q in raw]
    assert len(ids) == len(set(ids))
    known = {c.clause_id: d.loan_type for d in load_all() for c in d.clauses}
    prefix = {"common": "CM", "personal": "PL", "home": "HL", "education": "ED", "business": "BL",
              "vehicle": "VL"}  # fmt: skip
    for q in raw:
        assert q["split"] in ("dev", "test") and q["expected"]
        for cid in q["expected"]:
            assert cid in known, (q["id"], cid)
            # an expected clause must be reachable under the query's loan type filter
            assert known[cid] in ("common", q["loan_type"]), (q["id"], cid)
            assert cid.startswith(prefix[known[cid]])
    assert len(load_queries("dev")) >= 40 and len(load_queries("test")) >= 10


def test_metric_math() -> None:
    m = score_query(["A", "B"], ["X", "A", "Y", "B", "Z"])
    assert m["hit@1"] == 0 and m["hit@3"] == 1 and m["recall@3"] == 0.5 and m["recall@5"] == 1.0
    assert m["mrr"] == 0.5
    assert score_query(["A"], ["X", "Y"])["mrr"] == 0.0


def test_citation_validity_flags_wrong_type_inactive_and_unknown() -> None:
    known = {"CM-A": "common", "HL-A": "home"}
    good = [clause("CM-A", 1), clause("HL-A", 1, loan="home")]
    assert citation_validity(good, "home", known) == 1.0
    bad = [clause("HL-A", 1, loan="home")]
    assert citation_validity(bad, "personal", known) == 0.0
    assert citation_validity([clause("ZZ-A", 1)], "home", known) == 0.0


def test_check_targets_reports_misses() -> None:
    assert check_targets({"recall@5": 0.9}, {"recall@5": 0.8}) == []
    assert check_targets({"recall@5": 0.7}, {"recall@5": 0.8})


def test_baseline_file_has_recorded_targets() -> None:
    stored = json.loads(BASELINE_PATH.read_text())
    assert stored["baseline_dev"]["queries"] >= 40 and stored["targets"]


def test_queries_load_as_dataclass() -> None:
    q = load_queries("dev")[0]
    assert isinstance(q, Query) and q.expected
