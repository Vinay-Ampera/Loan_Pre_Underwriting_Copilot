"""Insights (Stage 12 Part B): counted from the case records with SQL. No model is called.

Every panel is scoped to cases **created** in [start, end) and, optionally, one loan type. The
same numbers serve two readers: the admin gets case references (to open the cases) and officer
ids (to open an officer); the auditor gets neither, only counts, rule and clause ids and officer
names (decision 9, EDGE_CASES E-115). `strip_refs` makes the auditor's copy.

Times: "report ready after" is created -> `report_ready_at` (the latest report that waits for the
officer); "officer decided after" is `report_ready_at` -> the officer's action. Medians, not means,
so one forgotten case does not move the figure. Stop reasons are read from every stored report
version, so a stop that was later fixed still counts (E-114).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from app.scoring.evaluate import band_for
from app.scoring.rules import RuleSet

STAGE_LABEL = {"extraction": "Documents", "kyc": "KYC", "risk": "Income and credit",
               "policy": "Policy fit"}  # fmt: skip
BAND_OF = {"recommend_approve": "approve", "refer": "refer", "recommend_reject": "reject"}
TOP = 20  # rows in each table
CASES_PER_ROW = 25  # case references the admin can open from one row


@dataclass(frozen=True)
class Scope:
    start: datetime | None = None
    end: datetime | None = None  # exclusive
    loan_type: str | None = None


SCOPE_CTE = """scope AS (
    SELECT c.* FROM cases c
     WHERE (CAST(:start AS timestamptz) IS NULL OR c.created_at >= CAST(:start AS timestamptz))
       AND (CAST(:end AS timestamptz) IS NULL OR c.created_at < CAST(:end AS timestamptz))
       AND (CAST(:lt AS text) IS NULL OR c.loan_type = CAST(:lt AS text)))"""
# the officer's one action on a case (confirm or override)
ACTION = """LEFT JOIN LATERAL (
    SELECT o.action, o.officer_id, o.original_recommendation, o.final_decision, o.created_at
      FROM officer_actions o WHERE o.case_id = s.id ORDER BY o.created_at LIMIT 1) act ON true"""
CASE_LIST = "jsonb_agg(DISTINCT jsonb_build_object('id', s.id, 'case_no', s.case_no))"


def _rows(conn: Connection, scope: Scope, sql: str, **extra: Any) -> list[Any]:
    params = {"start": scope.start, "end": scope.end, "lt": scope.loan_type, **extra}
    return list(conn.execute(text(f"WITH {SCOPE_CTE} {sql}"), params))


def _secs(v: Any) -> float | None:
    return None if v is None else round(float(v), 1)


def _cases(v: Any) -> list[dict[str, str]]:
    items = sorted(v or [], key=lambda c: c["case_no"])
    return [{"id": str(c["id"]), "case_no": c["case_no"]} for c in items[:CASES_PER_ROW]]


# --- panels ---------------------------------------------------------------------------------
def time_to_decide(conn: Connection, scope: Scope) -> dict[str, Any]:
    ready_s = "extract(epoch FROM s.report_ready_at - s.created_at)::float8"
    decide_s = "extract(epoch FROM act.created_at - s.report_ready_at)::float8"
    head = _rows(conn, scope, f"""
        SELECT count(s.report_ready_at) AS ready_n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY {ready_s}) AS ready_median,
               max({ready_s}) AS ready_max,
               count(act.created_at) FILTER (WHERE s.report_ready_at IS NOT NULL) AS decided_n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY {decide_s}) AS decided_median,
               max({decide_s}) AS decided_max
          FROM scope s {ACTION}""")[0]  # fmt: skip
    by_loan = _rows(conn, scope, f"""
        SELECT s.loan_type, count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY {decide_s}) AS median
          FROM scope s {ACTION}
         WHERE act.created_at IS NOT NULL AND s.report_ready_at IS NOT NULL
         GROUP BY 1 ORDER BY 1""")  # fmt: skip
    by_officer = _rows(conn, scope, f"""
        SELECT act.officer_id, u.name, count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY {decide_s}) AS median
          FROM scope s {ACTION} JOIN users u ON u.id = act.officer_id
         WHERE s.report_ready_at IS NOT NULL
         GROUP BY 1, 2 ORDER BY 2""")  # fmt: skip
    return {
        "report_ready": {"n": head.ready_n, "median_s": _secs(head.ready_median),
                         "slowest_s": _secs(head.ready_max)},
        "officer_decided": {"n": head.decided_n, "median_s": _secs(head.decided_median),
                            "slowest_s": _secs(head.decided_max)},
        "by_loan_type": [{"loan_type": r.loan_type, "n": r.n, "median_s": _secs(r.median)}
                         for r in by_loan],
        "by_officer": [{"officer_id": str(r.officer_id), "officer": r.name, "n": r.n,
                        "median_s": _secs(r.median)} for r in by_officer],
    }  # fmt: skip


def funnel(conn: Connection, scope: Scope) -> dict[str, int]:
    r = _rows(conn, scope, f"""
        SELECT count(*) AS created, count(s.submitted_at) AS submitted,
               count(s.report_ready_at) AS report_ready, count(act.action) AS decided,
               count(*) FILTER (WHERE act.action = 'confirm') AS confirmed,
               count(*) FILTER (WHERE act.action = 'override') AS changed,
               count(*) FILTER (WHERE s.status IN ('draft', 'uploaded', 'applicant_submitted'))
                   AS not_submitted,
               count(*) FILTER (WHERE s.status = 'running') AS running,
               count(*) FILTER (WHERE s.status = 'stopped') AS stopped,
               count(*) FILTER (WHERE s.status = 'awaiting_confirmation') AS waiting
          FROM scope s {ACTION}""")[0]  # fmt: skip
    return dict(r._mapping)


def agreement(conn: Connection, scope: Scope) -> dict[str, Any]:
    rows = _rows(conn, scope, f"""
        SELECT s.loan_type, act.original_recommendation AS rec, act.action, count(*) AS n
          FROM scope s {ACTION} WHERE act.action IS NOT NULL GROUP BY 1, 2, 3""")  # fmt: skip
    corrections = _rows(
        conn, scope, "SELECT count(*) AS n FROM scope s JOIN admin_actions a ON a.case_id = s.id"
    )[0].n

    def tally(key: str) -> list[dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            k = r.loan_type if key == "loan_type" else BAND_OF.get(r.rec, r.rec)
            row = out.setdefault(k, {key: k, "confirmed": 0, "changed": 0})
            row["confirmed" if r.action == "confirm" else "changed"] += r.n
        return [out[k] for k in sorted(out)]

    confirmed = sum(r.n for r in rows if r.action == "confirm")
    changed = sum(r.n for r in rows if r.action == "override")
    return {"confirmed": confirmed, "changed": changed, "admin_corrections": corrections,
            "by_loan_type": tally("loan_type"), "by_band": tally("band")}  # fmt: skip


def changed_rules(conn: Connection, scope: Scope) -> list[dict[str, Any]]:
    """The rules that failed in cases the officer changed, with the direction of the change."""
    rows = _rows(conn, scope, f"""
        SELECT r.rule_id, r.clause_id, act.original_recommendation AS rec,
               act.final_decision AS final, count(DISTINCT s.id) AS n, {CASE_LIST} AS cases
          FROM scope s {ACTION}
          JOIN stage_runs sr ON sr.case_id = s.id
          JOIN rule_results r ON r.stage_run_id = sr.id AND NOT r.passed
         WHERE act.action = 'override'
         GROUP BY 1, 2, 3, 4 ORDER BY n DESC, 1, 3, 4 LIMIT :top""", top=TOP)  # fmt: skip
    return [{"rule_id": r.rule_id, "clause_id": r.clause_id,
             "from": BAND_OF.get(r.rec, r.rec), "to": r.final, "n": r.n,
             "cases": _cases(r.cases)} for r in rows]  # fmt: skip


def stop_reasons(conn: Connection, scope: Scope) -> list[dict[str, Any]]:
    """Every stored report version that stopped, by stage and the rule that stopped it (E-114)."""
    findings = """CASE WHEN jsonb_typeof(rp.report_json->'findings') = 'array'
                       THEN rp.report_json->'findings' ELSE '[]'::jsonb END"""
    rows = _rows(conn, scope, f"""
        SELECT rp.report_json->>'stopped_stage' AS stage, f->>'rule_id' AS rule_id,
               f->>'clause_id' AS clause_id, count(DISTINCT s.id) AS n, {CASE_LIST} AS cases
          FROM scope s JOIN reports rp ON rp.case_id = s.id
         CROSS JOIN LATERAL jsonb_array_elements({findings}) f
         WHERE rp.report_json->>'stopped_stage' IS NOT NULL AND f->>'severity' = 'hard_fail'
         GROUP BY 1, 2, 3 ORDER BY n DESC, 1, 2 LIMIT :top""", top=TOP)  # fmt: skip
    return [{"stage": r.stage, "stage_label": STAGE_LABEL.get(r.stage, r.stage),
             "rule_id": r.rule_id, "clause_id": r.clause_id, "n": r.n,
             "cases": _cases(r.cases)} for r in rows]  # fmt: skip


def precedent_use(conn: Connection, scope: Scope, rs: RuleSet) -> dict[str, Any]:
    """Cases an approved precedent's bonus reached, and those it moved to another band. The
    band without the bonus is worked out by the scoring code's own `band_for`."""
    rows = _rows(conn, scope, """
        , used AS (SELECT DISTINCT s.id, s.case_no FROM scope s
                     JOIN precedent_uses pu ON pu.case_id = s.id)
        SELECT DISTINCT ON (u.id) u.id, u.case_no,
               (r.report_json->>'total_score')::float AS total,
               coalesce((r.report_json->>'precedent_bonus')::float, 0) AS bonus,
               r.report_json->>'band' AS band
          FROM used u LEFT JOIN reports r ON r.case_id = u.id
         ORDER BY u.id, r.version DESC""")  # fmt: skip
    moved = [r for r in rows if r.bonus and r.total is not None and r.band
             and band_for(r.total - r.bonus, rs) != r.band]  # fmt: skip
    return {"reached": len(rows), "moved": len(moved),
            "cases": _cases([{"id": r.id, "case_no": r.case_no} for r in rows]),
            "moved_cases": _cases([{"id": r.id, "case_no": r.case_no} for r in moved])}  # fmt: skip


def clause_titles(conn: Connection, ids: set[str]) -> dict[str, dict[str, str | None]]:
    """Title and policy document of each clause in the policy in force (for labels and links)."""
    if not ids:
        return {}
    rows = conn.execute(
        text("""SELECT DISTINCT ON (c.clause_id) c.clause_id, c.metadata->>'title' AS title,
                       d.loan_type AS doc
                  FROM policy_chunks c JOIN policy_documents d ON d.id = c.policy_document_id
                 WHERE d.status = 'active' AND c.clause_id = ANY(:ids)
                 ORDER BY c.clause_id"""),
        {"ids": sorted(ids)},
    )  # fmt: skip
    return {r.clause_id: {"title": r.title, "doc": r.doc} for r in rows}


# --- the page -------------------------------------------------------------------------------
def build(conn: Connection, scope: Scope, rs: RuleSet) -> dict[str, Any]:
    """Every panel, with case references (the admin's copy)."""
    rules = changed_rules(conn, scope)
    stops = stop_reasons(conn, scope)
    clauses = clause_titles(conn, {r["clause_id"] for r in rules + stops if r["clause_id"]})
    for r in rules + stops:
        c = clauses.get(r["clause_id"] or "", {})
        r["clause_title"], r["clause_doc"] = c.get("title"), c.get("doc")
    return {
        "scope": {"start": scope.start, "end": scope.end, "loan_type": scope.loan_type},
        "time_to_decide": time_to_decide(conn, scope),
        "funnel": funnel(conn, scope),
        "agreement": agreement(conn, scope),
        "changed_rules": rules,
        "stop_reasons": stops,
        "precedents": precedent_use(conn, scope, rs),
    }


def strip_refs(page: dict[str, Any]) -> dict[str, Any]:
    """The auditor's copy: no case id, no case reference, no officer id (E-115)."""
    out = {**page}
    out["time_to_decide"] = {**page["time_to_decide"], "by_officer": [
        {k: v for k, v in r.items() if k != "officer_id"}
        for r in page["time_to_decide"]["by_officer"]]}  # fmt: skip
    out["changed_rules"] = [{k: v for k, v in r.items() if k != "cases"}
                            for r in page["changed_rules"]]  # fmt: skip
    out["stop_reasons"] = [{k: v for k, v in r.items() if k != "cases"}
                           for r in page["stop_reasons"]]  # fmt: skip
    out["precedents"] = {k: page["precedents"][k] for k in ("reached", "moved")}
    return out


def officer_own(conn: Connection, officer_id: Any) -> dict[str, Any]:
    """An officer's own decisions in the last 30 days, for their Home page. Never anyone else's."""
    r = conn.execute(
        text("""SELECT count(*) AS n, percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY extract(epoch FROM o.created_at - c.report_ready_at)::float8) AS median
                  FROM officer_actions o JOIN cases c ON c.id = o.case_id
                 WHERE o.officer_id = :me AND o.created_at > now() - interval '30 days'
                   AND c.report_ready_at IS NOT NULL"""),
        {"me": officer_id},
    ).one()  # fmt: skip
    return {"decided_30d": r.n, "median_decision_s": _secs(r.median)}
