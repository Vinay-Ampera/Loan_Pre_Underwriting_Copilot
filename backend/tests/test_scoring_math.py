from datetime import date

import pytest

from app.scoring import finance, matching


def test_emi_matches_known_value() -> None:
    # 10 lakh at 12% over 12 months: 88,848.79 (standard reducing-balance EMI)
    assert finance.emi(1_000_000, 12, 12) == pytest.approx(88_848.79, abs=0.01)
    assert finance.emi(120_000, 0, 12) == 10_000
    with pytest.raises(ValueError):
        finance.emi(1000, 10, 0)


def test_age_changes_on_the_birthday() -> None:
    dob = date(1990, 5, 14)
    assert finance.age_on(dob, date(2026, 5, 13)) == 35
    assert finance.age_on(dob, date(2026, 5, 14)) == 36


def test_add_months_clamps_to_month_end() -> None:
    assert finance.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert finance.add_months(date(2026, 10, 20), 300) == date(2051, 10, 20)
    assert finance.add_months(date(2026, 10, 20), -12) == date(2025, 10, 20)


def test_age_at_maturity_uses_application_date_plus_tenure() -> None:
    maturity = finance.add_months(date(2026, 10, 20), 300)
    assert finance.age_on(date(1998, 9, 7), maturity) == 53


def test_foir_ltv_dti_and_zero_denominators() -> None:
    assert finance.foir_pct(10_000, 15_000, 62_500) == 40.0
    assert finance.foir_pct(1, 1, 0) is None
    assert finance.ltv_pct(2_250_000, 2_810_000) == 80.1
    assert finance.ltv_pct(1, 0) is None
    assert finance.dti_pct(600_000, 1_200_000) == 50.0
    assert finance.ratio(1, 0) is None


def test_name_match_ignores_order_case_and_titles() -> None:
    assert matching.name_match("Rekha Sinha", "SINHA REKHA") == 100
    assert matching.name_match("Rekha Sinha", "Mrs. Rekha Sinha") == 100
    assert matching.name_match("Rekha Sinha", None) is None


def test_name_match_thresholds_separate_variant_from_different_person() -> None:
    variant = matching.name_match("Rekha Sinha", "Rekha Sinhaa")
    other = matching.name_match("Rekha Sinha", "Mahesh Kumar")
    assert variant is not None and variant >= 85
    assert other is not None and other < 60


def test_address_match_keeps_punctuation_significant() -> None:
    same = matching.address_match("12, Park Road, Pune 411001", "12 Park Road Pune 411001")
    different = matching.address_match("12, Park Road, Pune 411001", "88, Canal Road, Pune")
    assert same is not None and same > 90
    assert different is not None and different < 70


def test_pan_match_is_exact_not_fuzzy() -> None:
    assert matching.pan_match("abcps1234f ", "ABCPS1234F") is True
    assert matching.pan_match("ABCPS1234F", "ABCPS1234G") is False
    assert matching.pan_match(None, "ABCPS1234F") is None


def test_dob_match_across_formats() -> None:
    dob = date(1990, 5, 14)
    assert matching.dob_match(dob, ["1990-05-14", "14/05/1990", "14-May-1990"]) is True
    assert matching.dob_match(dob, ["1990-05-14", "1991-05-14"]) is False
    assert matching.dob_match(dob, [None, ""]) is None
