"""Mock identity (PAN/Aadhaar), bureau (CIBIL), GST and Udyam services.

All backed by synthetic records. A real integration later replaces `RecordStore` or the
service classes; callers only see the models below. Aadhaar is only ever looked up by hash.
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from app.core.config import REPO_ROOT

DEFAULT_RECORDS_DIR = REPO_ROOT / "data" / "synthetic" / "output" / "records"


class IdentityRecord(BaseModel):
    pan: str
    name: str
    dob: date
    aadhaar_hash: str
    address: str


class BureauRecord(BaseModel):
    pan: str
    cibil_score: int
    active_loans: list[dict[str, Any]] = []
    enquiries: list[dict[str, Any]] = []


class GstRecord(BaseModel):
    gstin: str
    legal_name: str
    pan: str
    turnover_12m: float
    filings: list[dict[str, Any]] = []


class UdyamRecord(BaseModel):
    udyam_no: str
    legal_name: str
    pan: str
    registered_on: date


def aadhaar_hash(aadhaar: str) -> str:
    return hashlib.sha256(aadhaar.encode()).hexdigest()


class RecordStore:
    """JSON files in one directory: identity.json, bureau.json, gst.json, udyam.json."""

    def __init__(self, directory: Path = DEFAULT_RECORDS_DIR) -> None:
        self.directory = directory

    def load[T: BaseModel](self, name: str, model: type[T]) -> list[T]:
        path = self.directory / f"{name}.json"
        if not path.exists():
            return []
        return TypeAdapter(list[model]).validate_python(json.loads(path.read_text()))  # type: ignore[valid-type]


class IdentityService:
    def __init__(self, store: RecordStore | None = None) -> None:
        records = (store or RecordStore()).load("identity", IdentityRecord)
        self._by_pan = {r.pan: r for r in records}

    def lookup(self, pan: str) -> IdentityRecord | None:
        return self._by_pan.get(pan)

    def verify(self, pan: str, name: str, dob: date, aadhaar: str | None = None) -> bool:
        """True when PAN exists and name (case-insensitive), DOB and optional Aadhaar agree."""
        rec = self._by_pan.get(pan)
        if rec is None or rec.dob != dob or rec.name.casefold() != name.casefold():
            return False
        return aadhaar is None or rec.aadhaar_hash == aadhaar_hash(aadhaar)


class BureauService:
    def __init__(self, store: RecordStore | None = None) -> None:
        records = (store or RecordStore()).load("bureau", BureauRecord)
        self._by_pan = {r.pan: r for r in records}

    def report(self, pan: str) -> BureauRecord | None:
        return self._by_pan.get(pan)


class GstService:
    def __init__(self, store: RecordStore | None = None) -> None:
        records = (store or RecordStore()).load("gst", GstRecord)
        self._by_gstin = {r.gstin: r for r in records}

    def lookup(self, gstin: str) -> GstRecord | None:
        return self._by_gstin.get(gstin)


class UdyamService:
    def __init__(self, store: RecordStore | None = None) -> None:
        records = (store or RecordStore()).load("udyam", UdyamRecord)
        self._by_no = {r.udyam_no: r for r in records}

    def lookup(self, udyam_no: str) -> UdyamRecord | None:
        return self._by_no.get(udyam_no)
