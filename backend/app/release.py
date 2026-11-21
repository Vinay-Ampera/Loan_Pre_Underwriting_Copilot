"""Release manifest (Stage 11): what a release runs with, written next to the docs so a git tag can
be traced to its models, prompts, rules and policies.

    python -m app.release --tag v1.0.0            uses the database for the saved AI configuration
                                                  and the policy versions in force
    python -m app.release --tag v1.0.0 --no-db    file defaults only (no database needed)

Writes `docs/releases/<tag>.json` and prints the `git tag` command. It never writes to git and
never reads a key: models are named by their provider ids, keys by nothing at all.
"""

import argparse
import json
import subprocess
import tomllib
from datetime import UTC, datetime
from typing import Any

from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text

from app.core.config import REPO_ROOT
from app.db.migrate import alembic_config
from app.rag.config import load_rag_config
from app.rag.policy_loader import load_all
from app.scoring.rules import load_rules
from app.services import ai_config

RELEASES = REPO_ROOT / "docs" / "releases"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True, timeout=10).stdout.strip()  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return ""


def _models(snapshot: ai_config.Snapshot) -> dict[str, dict[str, Any]]:
    ids = {name: spec["model"] for name, spec in ai_config.catalogue().items()}
    return {
        role: {"primary": ids.get(spec["primary"], spec["primary"]),
               "fallbacks": [ids.get(f, f) for f in spec["fallbacks"]]}
        for role, spec in sorted(snapshot.config["roles"].items())
    }  # fmt: skip


def _policies(engine: Engine | None) -> dict[str, str]:
    if engine is None:
        return {d.loan_type: d.version for d in load_all()}
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT loan_type, version FROM policy_documents WHERE status = 'active'")
        )
        return {r.loan_type: r.version for r in rows}


def manifest(tag: str, engine: Engine | None = None) -> dict[str, Any]:
    snapshot = ai_config.Snapshot()
    if engine is not None:
        with engine.connect() as conn:
            snapshot = ai_config.load(conn)
    rules = load_rules()
    rag = load_rag_config()
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return {
        "tag": tag,
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "app_version": pyproject["project"]["version"],
        "commit": _git("rev-parse", "HEAD"),
        "uncommitted_changes": bool(_git("status", "--porcelain")),
        "migration_head": ScriptDirectory.from_config(alembic_config()).get_current_head(),
        "rules": {"version": rules.version, "checksum": rules.checksum},
        "policy_versions": dict(sorted(_policies(engine).items())),
        "policy_source": "database" if engine is not None else "files",
        "ai_config_version": snapshot.config_version,
        "models_on": snapshot.llm_enabled,
        "models": _models(snapshot),
        "prompt_versions": snapshot.prompt_versions(),
        "local_models": {"embedding": rag.embedding_model, "reranker": rag.reranker_model},
    }


def main() -> None:
    from app.core.config import get_settings  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Write the release manifest for a tag.")
    ap.add_argument("--tag", required=True, help="the release tag, for example v1.0.0")
    ap.add_argument("--no-db", action="store_true", help="file defaults only")
    args = ap.parse_args()
    engine = None if args.no_db else create_engine(get_settings().sqlalchemy_url())
    try:
        data = manifest(args.tag, engine)
    finally:
        if engine is not None:
            engine.dispose()
    RELEASES.mkdir(parents=True, exist_ok=True)
    path = RELEASES / f"{args.tag}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(REPO_ROOT)}")
    if data["uncommitted_changes"]:
        print("Note: there are uncommitted changes; commit them (with this file) before tagging.")
    models = ", ".join(f"{r} {m['primary']}" for r, m in data["models"].items())
    print("To tag the release (run it yourself):")
    print(f'  git tag -a {args.tag} -m "Pramaan {args.tag}: rules {data["rules"]["version"]}, '
          f'policies {", ".join(f"{k} {v}" for k, v in data["policy_versions"].items())}; '
          f'models {models}"')  # fmt: skip


if __name__ == "__main__":
    main()
