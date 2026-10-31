"""Tiny unit-test fixtures, separate from the 100 cases: `python -m synthetic.fixtures`.

Writes backend/tests/fixtures/. All values are synthetic and small enough to commit.
"""

import json
import random
from datetime import date, datetime

from app.core.config import REPO_ROOT
from app.intake.validators import gstin_check_char, verhoeff_check_digit
from app.services.mock_services import aadhaar_hash
from synthetic import render, variants
from synthetic.finance import StatementProfile, build_statement

OUT = REPO_ROOT / "backend" / "tests" / "fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)

    good_aadhaar = "23456789012" + verhoeff_check_digit("23456789012")
    first14 = "27ABCPK1234F1Z"
    ids = {
        "pan_valid": [{"pan": "ABCPK1234F", "surname": "Kumar"}, {"pan": "ZZZCK0001A", "surname": "Khan"}],
        "pan_invalid": ["ABCPK12345", "abcpk1234f", "ABCXK1234F", "ABC1K1234F"],
        "aadhaar_valid": [good_aadhaar],
        "aadhaar_invalid": [good_aadhaar[:-1] + "0" if good_aadhaar[-1] != "0" else good_aadhaar[:-1] + "1",
                            "123456789012", "2345678901"],  # bad checksum, first digit 1, 10 digits
        "gstin_valid": [first14 + gstin_check_char(first14)],
        "gstin_invalid": [first14 + ("0" if gstin_check_char(first14) != "0" else "1")],
        "udyam_valid": ["UDYAM-MH-12-1234567"],
        "udyam_invalid": ["UDYAM-MH-12-123456", "UDYAM-M1-12-1234567"],
    }  # fmt: skip
    (OUT / "ids.json").write_text(json.dumps(ids, indent=2))

    payslip = dict(employer="Orchid Textiles Ltd", employee="Test Person", designation="Executive", emp_id="E1001",
                   pan="ABCPK1234F", doj="01-Jan-2021", month_label="September 2026", bank_last4="1234",
                   earnings={"Basic": 20000, "HRA": 8000, "Special allowance": 12000},
                   deductions={"Provident fund": 2400, "Professional tax": 200, "Income tax (TDS)": 2400},
                   gross=40000, total_deductions=5000, net=35000)  # fmt: skip
    clean = render.payslip(payslip)
    (OUT / "payslip_clean.pdf").write_bytes(clean)
    (OUT / "payslip_tampered.pdf").write_bytes(
        variants.tamper_metadata(clean, rng, datetime(2026, 9, 28))
    )
    (OUT / "payslip_photo_mild.jpg").write_bytes(variants.photo_variant(clean, "mild", rng)[0])
    (OUT / "password_protected.pdf").write_bytes(variants.encrypt_pdf(clean, "pw-synthetic"))

    txns = build_statement(rng, StatementProfile(months=3, end_month=date(2026, 9, 1), income_per_month=35000,
                                                 kind="salary", employer="Orchid Textiles Ltd", returns=1,
                                                 existing_emis=[("Finserv Capital", 4000)]))  # fmt: skip
    stmt = render.bank_statement(
        "heritage",
        dict(bank="State Heritage Bank", holder="Test Person", account_no="1234567890", address="1 Test Road, Pune",
             period_from=date(2026, 7, 1), period_to=date(2026, 9, 30), ifsc="SHB0012345"),
        txns,
    )  # fmt: skip
    (OUT / "statement_digital.pdf").write_bytes(stmt)
    (OUT / "statement_scanned.pdf").write_bytes(variants.scanned_pdf(stmt, rng))

    records = {
        "identity": [{"pan": "ABCPK1234F", "name": "Test Kumar", "dob": "1990-04-12",
                      "aadhaar_hash": aadhaar_hash(good_aadhaar), "address": "1 Test Road, Pune"}],
        "bureau": [{"pan": "ABCPK1234F", "cibil_score": 742,
                    "active_loans": [{"lender": "Finserv Capital", "emi": 4000}], "enquiries": []}],
        "gst": [{"gstin": ids["gstin_valid"][0], "legal_name": "Test Kumar Traders", "pan": "ABCPK1234F",
                 "turnover_12m": 5000000.0, "filings": []}],
        "udyam": [{"udyam_no": "UDYAM-MH-12-1234567", "legal_name": "Test Kumar Traders", "pan": "ABCPK1234F",
                   "registered_on": "2022-02-20"}],
    }  # fmt: skip
    rec_dir = OUT / "records"
    rec_dir.mkdir(exist_ok=True)
    for name, rows in records.items():
        (rec_dir / f"{name}.json").write_text(json.dumps(rows, indent=2))
    print(f"fixtures written to {OUT}")


if __name__ == "__main__":
    main()
