import pytest

from app.intake.validators import (
    aadhaar_valid,
    gstin_check_char,
    gstin_valid,
    pan_valid,
    udyam_valid,
    verhoeff_check_digit,
    verhoeff_valid,
)


def test_verhoeff_known_vector() -> None:
    # classic textbook example: 236 -> check digit 3
    assert verhoeff_check_digit("236") == "3"
    assert verhoeff_valid("2363")
    assert not verhoeff_valid("2364")


def test_aadhaar_roundtrip_and_rules() -> None:
    payload = "23456789012"
    number = payload + verhoeff_check_digit(payload)
    assert aadhaar_valid(number)
    wrong = number[:-1] + str((int(number[-1]) + 1) % 10)
    assert not aadhaar_valid(wrong)
    assert not aadhaar_valid("1" + number[1:])  # first digit must be 2-9
    assert not aadhaar_valid(number[:-1])  # 11 digits


@pytest.mark.parametrize(
    ("pan", "surname", "ok"),
    [
        ("ABCPK1234F", "Kumar", True),
        ("ABCPK1234F", "Sharma", False),  # 5th letter must be surname initial
        ("ABCCK1234F", "Sharma", True),  # company: surname rule does not apply
        ("ABCXK1234F", None, False),  # bad holder type
        ("ABCPK12345", None, False),
        ("abcpk1234f", None, False),
    ],
)
def test_pan(pan: str, surname: str | None, ok: bool) -> None:
    assert pan_valid(pan, surname) is ok


def test_gstin_checksum_and_pan_link() -> None:
    first14 = "27ABCPK1234F1Z"
    gstin = first14 + gstin_check_char(first14)
    assert gstin_valid(gstin)
    assert gstin_valid(gstin, pan="ABCPK1234F")
    assert not gstin_valid(gstin, pan="ABCPK1234G")
    bad = gstin[:-1] + ("0" if gstin[-1] != "0" else "1")
    assert not gstin_valid(bad)


def test_udyam() -> None:
    assert udyam_valid("UDYAM-MH-12-1234567")
    assert not udyam_valid("UDYAM-MH-12-123456")
