"""Which identity fields of a case's form were read from the PAN and Aadhaar cards (Part B).

`offer` reads the early-read result saved next to each card and proposes the five identity values
per person (`intake/prefill.py`). `marks` compares what the officer saved with that offer: a
field still equal to the offered value is "from documents"; a field typed over is the officer's
own. The marks go into the case form, onto the confirmation tick and into the report, so a match
against the very card a value was read from is never presented as an independent check.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.api.filestore import FileStore
from app.intake import readcache
from app.intake.models import ExtractedDocument
from app.intake.prefill import prefill, still_from_documents


def offer(conn: Connection, store: FileStore, case_id: UUID) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        text("""SELECT role, doc_type, file_path FROM documents
                WHERE case_id = :c AND status = 'accepted' AND role IS NOT NULL
                  AND doc_type IN ('pan_card', 'aadhaar') AND file_path IS NOT NULL
                ORDER BY uploaded_at, original_name"""), {"c": case_id})  # fmt: skip
    cards: dict[str, dict[str, ExtractedDocument]] = {}
    for r in rows:
        doc = readcache.peek(store.get_read_result(r.file_path))
        if doc is not None:
            cards.setdefault(r.role, {}).setdefault(r.doc_type, doc)
    return prefill(cards)


def marks(
    offered: dict[str, dict[str, Any]], applicants: list[dict[str, Any]]
) -> dict[str, list[str]]:  # fmt: skip
    out: dict[str, list[str]] = {}
    for a in applicants:
        kept = still_from_documents(offered.get(a["role"], {}).get("values", {}), a)
        if kept:
            out[a["role"]] = kept
    return out
