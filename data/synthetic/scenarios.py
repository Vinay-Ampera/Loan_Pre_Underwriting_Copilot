"""The 100-case plan: which loan type, split, scenario kind and target score each case has."""

from dataclasses import dataclass

# kind: score | fix_* | elig_* | tamper.  Score cases carry an exact target total.
DEV_PLAN: list[tuple[str, float | None]] = [
    ("score", 100), ("score", 85), ("score", 67), ("score", 55), ("score", 40), ("score", 30),
    ("score", 92), ("score", 62),
    ("fix_kyc_missing", None), ("fix_name_mismatch", None),
    ("elig_age_over", None), ("elig_cibil_low", None), ("tamper", None),
]  # fmt: skip
TEST_PLAN: dict[str, list[tuple[str, float | None]]] = {
    "a": [("score", 98), ("score", 85), ("score", 72), ("score", 55), ("score", 40),
          ("fix_pan_invalid", None), ("fix_aadhaar_invalid", None), ("elig_nonresident", None),
          ("tamper", None)],
    "b": [("score", 98), ("score", 85), ("score", 72), ("score", 55), ("score", 40),
          ("fix_pan_invalid", None), ("fix_dob_mismatch", None), ("elig_age_under", None),
          ("tamper", None)],
}  # fmt: skip
EDU_DEV: list[tuple[str, float | None]] = [
    ("score", 100), ("score", 85), ("score", 55), ("score", 30),
    ("fix_kyc_missing", None), ("fix_name_mismatch", None), ("elig_cibil_low", None),
    ("tamper", None),
]  # fmt: skip
EDU_TEST: list[tuple[str, float | None]] = [
    ("score", 98), ("score", 67), ("fix_pan_invalid", None), ("elig_age_over", None),
]  # fmt: skip

PREFIX = {"personal": "PL", "home": "HL", "education": "ED", "business": "BL", "vehicle": "VL"}


@dataclass(frozen=True)
class Scenario:
    case_id: str
    split: str
    loan_type: str
    kind: str
    target: float | None
    co_applicant: bool


def all_scenarios() -> list[Scenario]:
    out: list[Scenario] = []
    for loan in ("personal", "home", "vehicle", "business", "education"):
        if loan == "education":
            plans = {"dev": EDU_DEV, "test": EDU_TEST}
        else:
            variant = "a" if loan in ("personal", "vehicle") else "b"
            plans = {"dev": DEV_PLAN, "test": TEST_PLAN[variant]}
        for split, plan in plans.items():
            for i, (kind, target) in enumerate(plan, 1):
                co = loan == "education" or (loan == "home" and i % 3 == 0)
                out.append(
                    Scenario(f"SYN-{PREFIX[loan]}-{split[0].upper()}{i:02d}", split, loan, kind,
                             target, co)
                )  # fmt: skip
    return out
