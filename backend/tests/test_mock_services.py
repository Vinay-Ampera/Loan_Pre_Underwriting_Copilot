import json
from datetime import date
from pathlib import Path

import pytest

from app.services.mock_services import (
    BureauService,
    GstService,
    IdentityService,
    RecordStore,
    UdyamService,
    aadhaar_hash,
)

FIXTURES = Path(__file__).parent / "fixtures"
IDS = json.loads((FIXTURES / "ids.json").read_text())
AADHAAR = IDS["aadhaar_valid"][0]
GSTIN = IDS["gstin_valid"][0]


@pytest.fixture(scope="module")
def store() -> RecordStore:
    return RecordStore(FIXTURES / "records")


def test_identity_verify(store: RecordStore) -> None:
    svc = IdentityService(store)
    rec = svc.lookup("ABCPK1234F")
    assert rec is not None and rec.name == "Test Kumar"
    assert svc.verify("ABCPK1234F", "test kumar", date(1990, 4, 12))
    assert not svc.verify("ABCPK1234F", "Test Kumar", date(1990, 4, 13))
    assert not svc.verify("ABCPK1234F", "Someone Else", date(1990, 4, 12))
    assert svc.lookup("ZZZZZ9999Z") is None


def test_identity_aadhaar_only_by_hash(store: RecordStore) -> None:
    svc = IdentityService(store)
    rec = svc.lookup("ABCPK1234F")
    assert rec is not None
    assert len(rec.aadhaar_hash) == 64 and AADHAAR not in rec.aadhaar_hash
    assert rec.aadhaar_hash == aadhaar_hash(AADHAAR)
    assert "aadhaar" not in rec.model_dump()  # there is no plaintext field to leak
    assert svc.verify("ABCPK1234F", "Test Kumar", date(1990, 4, 12), aadhaar=AADHAAR)
    assert not svc.verify("ABCPK1234F", "Test Kumar", date(1990, 4, 12), aadhaar="999999999999")


def test_bureau_gst_udyam(store: RecordStore) -> None:
    bureau = BureauService(store).report("ABCPK1234F")
    assert bureau is not None and bureau.cibil_score == 742
    gst = GstService(store)
    rec = gst.lookup(GSTIN)
    assert rec is not None and rec.pan == "ABCPK1234F"
    assert gst.lookup("27ZZZZZ0000Z1Z0") is None
    assert UdyamService(store).lookup("UDYAM-MH-12-1234567") is not None
    assert UdyamService(store).lookup("UDYAM-MH-12-0000000") is None


def test_missing_records_dir_gives_empty_services(tmp_path: Path) -> None:
    assert IdentityService(RecordStore(tmp_path)).lookup("ABCPK1234F") is None
