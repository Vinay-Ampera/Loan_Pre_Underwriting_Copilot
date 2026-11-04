"""The early read, kept (EDGE_CASES E-54, Stage 10 item 1).

When a file is accepted at the intake desk it is read once (text layer or OCR), classified and
its fields extracted locally. The result is saved next to the file as a small JSON object keyed by
the file's SHA-256. Extraction loads it instead of reading the file again.

What is saved: the upload checks, the extracted document (fields, quality flags, tamper hints,
issues, transactions) and the list of missing fields. What is **not** saved: the raw text of the
page. A model pass that fills gaps needs the text, so Extraction reads the file afresh in that
one case (only when a model is on and fields are missing); everything else reuses the result.

A saved result is used only if its hash matches the bytes and its as-of date matches the
application date, because the date checks depend on it. Anything else is ignored and the file is
read as before.
"""

import json
from datetime import date

from pydantic import ValidationError

from app.intake.models import ExtractedDocument, UploadCheck
from app.intake.pipeline import IntakeResult

READ_SUFFIX = ".read.json"
VERSION = 1


def dump(result: IntakeResult, as_of: date) -> bytes:
    body = {
        "v": VERSION,
        "sha256": result.sha256,
        "as_of": as_of.isoformat(),
        "upload": result.upload.model_dump(mode="json"),
        "document": None if result.document is None else result.document.model_dump(mode="json"),
        "missing": result.missing,
    }
    return json.dumps(body).encode()


def load(blob: bytes, sha256: str, as_of: date) -> IntakeResult | None:
    """The saved result, or None when it is unusable (other version, other bytes, other date)."""
    try:
        body = json.loads(blob)
        if body["v"] != VERSION or body["sha256"] != sha256 or body["as_of"] != as_of.isoformat():
            return None
        document = body["document"]
        return IntakeResult(
            upload=UploadCheck.model_validate(body["upload"]),
            document=None if document is None else ExtractedDocument.model_validate(document),
            raw_text="",
            missing=list(body["missing"]),
            sha256=sha256,
        )
    except (ValueError, KeyError, TypeError, ValidationError):
        return None


def peek(blob: bytes | None) -> ExtractedDocument | None:
    """The extracted document in a saved result, without checking hash or date (for the desk's
    own display and prefill, where the bytes are the ones just stored)."""
    if not blob:
        return None
    try:
        document = json.loads(blob)["document"]
        return None if document is None else ExtractedDocument.model_validate(document)
    except (ValueError, KeyError, TypeError, ValidationError):
        return None
