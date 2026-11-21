"""`python -m app.rag.reindex [--force] [--skip-rules]`: import the policy files and refresh the index.

Run it after editing a file in data/policy or data/rules. The database holds every policy version
(Stage 10c); a file is imported only when its version label is new, or when it edits the active
version it was imported as (see app/rag/index.py). Versions published from the knowledge base
screen are never overwritten by a file. It prints what changed per document, and refuses (and
rolls back) if a rule would cite a clause that is not in the active or scheduled policy.
"""

import argparse

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.seed import seed_rules
from app.rag.index import check_rule_clauses, reindex
from app.rag.policy_loader import load_all
from app.scoring.rules import load_rules


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-embed every clause")
    ap.add_argument("--skip-rules", action="store_true", help="do not reload the rules file")
    args = ap.parse_args()

    # every rule must point at a clause that exists in the files, or the files and rules drifted
    clauses = {c.clause_id for d in load_all() for c in d.clauses}
    missing = sorted({r.policy_clause for r in load_rules().rules} - clauses)
    if missing:
        raise SystemExit(f"rules cite clauses that are not in data/policy: {missing}")

    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.begin() as conn:  # one transaction: all or nothing
        report = reindex(conn, force=args.force)
        for lt in report.activated:
            print(f"{lt:10} a scheduled version reached its effective date and is now active")
        for d in report.docs:
            label = "new version" if d.new_version else "same version"
            print(
                f"{d.loan_type:10} {d.version} ({label}, {d.status or 'not imported'}): "
                f"+{len(d.added)} added, ~{len(d.changed)} changed, -{len(d.removed)} removed, "
                f"{d.unchanged} unchanged"
            )
            if d.note:
                print(f"           note: {d.note}")
            for tag, ids in (("added", d.added), ("changed", d.changed), ("removed", d.removed)):
                if ids:
                    print(f"           {tag}: {', '.join(ids)}")
        print(f"embedded {report.embedded} clause(s)")
        lost = check_rule_clauses(conn, load_rules())
        if lost:
            raise SystemExit(f"rules cite clauses missing from the policy in force: {lost}")
        if not args.skip_rules:
            seed_rules(conn)
            rs = load_rules()
            print(f"rules {rs.version} recorded (checksum {rs.checksum[:12]})")
        active = conn.execute(
            text("SELECT count(*) FROM policy_chunks c JOIN policy_documents d "
                 "ON d.id = c.policy_document_id WHERE d.active")
        ).scalar_one()  # fmt: skip
        print(f"{active} clause(s) active in the index")


if __name__ == "__main__":
    main()
