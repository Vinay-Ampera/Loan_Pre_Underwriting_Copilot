"""`python -m app.rag.reindex [--force] [--skip-rules]`: refresh the policy index and rule versions.

Run it after editing a file in data/policy or data/rules. It prints what changed per document.
"""

import argparse

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.seed import seed_rules
from app.rag.index import reindex
from app.rag.policy_loader import load_all
from app.scoring.rules import load_rules


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-embed every clause")
    ap.add_argument("--skip-rules", action="store_true", help="do not reload the rules file")
    args = ap.parse_args()

    # every rule must point at a clause that exists, or the index and rules have drifted
    clauses = {c.clause_id for d in load_all() for c in d.clauses}
    missing = sorted({r.policy_clause for r in load_rules().rules} - clauses)
    if missing:
        raise SystemExit(f"rules cite clauses that are not in data/policy: {missing}")

    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.begin() as conn:  # one transaction: all or nothing
        report = reindex(conn, force=args.force)
        for d in report.docs:
            label = "new version" if d.new_version else "same version"
            print(
                f"{d.loan_type:10} {d.version} ({label}): +{len(d.added)} added, "
                f"~{len(d.changed)} changed, -{len(d.removed)} removed, {d.unchanged} unchanged"
            )
            for tag, ids in (("added", d.added), ("changed", d.changed), ("removed", d.removed)):
                if ids:
                    print(f"           {tag}: {', '.join(ids)}")
        print(f"embedded {report.embedded} clause(s)")
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
