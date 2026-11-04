"""Who a file belongs to, what the inventory shows, and what the cards may fill in the form
(Stage 10, Parts A and B). Pure functions: no database, no files."""

from typing import Any

from app.intake.inventory import Item, Row, assign_roles, build_inventory, needed_from
from app.intake.models import DocType, ExtractedDocument, ExtractedField
from app.intake.prefill import IDENTITY_FIELDS, prefill, still_from_documents
from app.scoring.rules import load_rules

RS = load_rules()


def pan(name: str, number: str, dob: str = "1990-01-01") -> dict[str, Any]:
    return {"name": name, "pan": number, "dob": dob}


def aadhaar(name: str, dob: str = "1990-01-01") -> dict[str, Any]:
    return {
        "name": name,
        "dob": dob,
        "aadhaar": "123412341234",
        "address": "1 Park Rd, Pune 411001",
    }


def roles(items: list[Item], loan: str) -> dict[str, str | None]:
    co = {"education": "required", "home": "optional"}.get(loan, "not_allowed")
    who = ["primary", "co"] if co != "not_allowed" else ["primary"]
    return assign_roles(items, co_rule=co, needed_from=needed_from(RS, loan, who))


# --------------------------------------------------------------------------- assignment
def test_the_first_pan_is_the_primary_and_a_second_distinct_pan_the_co_applicant() -> None:
    out = roles([
        Item("p1", "pan_card", pan("Rahul Rao", "HOBPR1259X"), 0),
        Item("p2", "pan_card", pan("Meena Rao", "ABCDE1234F", "1970-05-05"), 1),
        Item("a2", "aadhaar", aadhaar("Meena Rao", "1970-05-05"), 2),
        Item("a1", "aadhaar", aadhaar("Rahul Rao"), 3),
        Item("s1", "payslip", {"employee": "Meena Rao", "pan": "ABCDE1234F"}, 4),
        Item("s2", "payslip", {"employee": "Rahul Rao", "pan": "HOBPR1259X"}, 5),
    ], "education")  # fmt: skip
    assert out == {
        "p1": "primary",
        "p2": "co",
        "a2": "co",
        "a1": "primary",
        "s1": "co",
        "s2": "primary",
    }


def test_a_second_pan_is_not_a_co_applicant_when_the_loan_has_none() -> None:
    out = roles([Item("p1", "pan_card", pan("A One", "AAAAA1111A"), 0),
                 Item("p2", "pan_card", pan("B Two", "BBBBB2222B"), 1)], "personal")  # fmt: skip
    assert out == {"p1": "primary", "p2": None}  # left for the officer, not guessed


def test_a_document_naming_a_stranger_stays_unassigned() -> None:
    out = roles([Item("p1", "pan_card", pan("Rahul Rao", "HOBPR1259X"), 0),
                 Item("s1", "payslip", {"employee": "Someone Else", "pan": "ZZZZZ9999Z"}, 1)],
                "personal")  # fmt: skip
    assert out["s1"] is None


def test_a_document_that_names_nobody_follows_the_checklist() -> None:
    items = [Item("p1", "pan_card", pan("Rahul Rao", "HOBPR1259X"), 0),
             Item("c1", "pan_card", pan("Meena Rao", "ABCDE1234F"), 1),
             Item("d", "admission_letter", {}, 2), Item("b", "bank_statement", {}, 3)]  # fmt: skip
    out = roles(items, "education")
    assert out["d"] == "primary" and out["b"] == "co"  # the bank statement is the earner's


def test_a_photo_is_assigned_only_when_there_is_one_person() -> None:
    one = roles([Item("p1", "pan_card", pan("A One", "AAAAA1111A"), 0), Item("ph", "photo", {}, 1)],
                "personal")  # fmt: skip
    two = roles([Item("p1", "pan_card", pan("A One", "AAAAA1111A"), 0),
                 Item("p2", "pan_card", pan("B Two", "BBBBB2222B"), 1),
                 Item("ph", "photo", {}, 2)], "education")  # fmt: skip
    assert one["ph"] == "primary" and two["ph"] is None


def test_an_aadhaar_with_no_pan_card_defines_the_primary() -> None:
    assert roles([Item("a", "aadhaar", aadhaar("Rahul Rao"), 0)], "personal") == {"a": "primary"}


def test_an_aadhaar_with_another_birth_date_does_not_join_the_person() -> None:
    out = roles([Item("p", "pan_card", pan("Rahul Rao", "HOBPR1259X", "1990-01-01"), 0),
                 Item("a", "aadhaar", aadhaar("Rahul Rao", "1991-02-02"), 1)], "personal")  # fmt: skip
    assert out["a"] is None


def test_the_officers_own_choice_is_never_changed() -> None:
    out = roles([Item("p1", "pan_card", pan("Rahul Rao", "HOBPR1259X"), 0, fixed="co"),
                 Item("p2", "pan_card", pan("Meena Rao", "ABCDE1234F"), 1)], "education")  # fmt: skip
    assert out == {"p1": "co", "p2": "primary"}  # the free seat goes to the other card


# --------------------------------------------------------------------------- inventory
def row(i: str, doc_type: str, role: str | None, **kw: Any) -> Row:
    return Row(id=i, name=f"{i}.pdf", status=kw.pop("status", "accepted"), doc_type=doc_type,
               classification=doc_type, role=role, **kw)  # fmt: skip


def inv(
    loan: str, rows: list[Row], employment: dict[str, str | None] | None = None
) -> dict[str, Any]:
    co = {"education": "required", "home": "optional"}.get(loan, "not_allowed")
    return build_inventory(RS, loan, rows, co_rule=co, employment=employment or {"primary": None, "co": None},
                           details={})  # fmt: skip


def test_missing_items_mark_kyc_as_essential_and_hold_back_employment_dependent_items() -> None:
    out = inv("personal", [row("p", "pan_card", "primary")])
    me = out["people"][0]
    assert [m["type"] for m in me["missing"] if m["essential"]] == ["aadhaar", "photo"]
    assert "payslip" not in [m["type"] for m in me["missing"]]  # depends on a claim not yet made
    assert {w["type"] for w in out["depends_on_employment"]} == {"payslip"}  # a personal loan
    home = inv("home", [row("p", "pan_card", "primary")])
    assert {w["type"] for w in home["depends_on_employment"]} >= {"payslip", "form16", "itr"}
    assert out["essential_missing"] == 2 and not out["complete"]


def test_once_employment_is_stated_the_dependent_items_count() -> None:
    out = inv("personal", [row("p", "pan_card", "primary")], {"primary": "salaried"})
    assert "payslip" in [m["type"] for m in out["people"][0]["missing"]]
    assert out["people"][0]["missing"][-1]["needed"] >= 1 and not out["depends_on_employment"]


def test_every_bucket_is_listed() -> None:
    rows = [row("pan", "pan_card", "primary"), row("sa", "sale_agreement", "primary"),
            row("u", "unknown", None), row("w", "aadhaar", None),
            row("x", "payslip", "primary", status="ignored", duplicate_of="s1.pdf", duplicate_kind="exact"),
            Row(id="r", name="r.jpg", status="rejected", doc_type="unknown", reject_code="blurry",
                message="too blurry")]  # fmt: skip
    out = inv("personal", rows, {"primary": "salaried"})
    me = out["people"][0]
    assert [r["doc_type"] for r in me["received"]] == ["pan_card"]
    assert [r["doc_type"] for r in me["extra"]] == [
        "sale_agreement"
    ]  # not needed for a personal loan
    assert [u["name"] for u in out["unrecognised"]] == ["u.pdf"]
    assert [u["name"] for u in out["unassigned"]] == ["w.pdf"]
    assert out["rejected"][0]["code"] == "blurry"
    assert out["duplicates"][0]["of"] == "s1.pdf"
    assert out["counts"]["received"] == 1 and out["counts"]["duplicates"] == 1


def test_the_co_applicant_appears_for_education_and_when_a_home_file_is_filed_to_them() -> None:
    assert [p["role"] for p in inv("education", [])["people"]] == ["primary", "co"]
    assert [p["role"] for p in inv("home", [])["people"]] == ["primary"]
    assert [p["role"] for p in inv("home", [row("c", "pan_card", "co")])["people"]] == [
        "primary",
        "co",
    ]


def test_an_income_paper_is_not_extra_while_employment_is_unknown() -> None:
    out = inv("home", [row("s", "payslip", "primary"), row("i", "itr", "primary")])
    assert not out["people"][0]["extra"]


# --------------------------------------------------------------------------- prefill
def card(doc_type: DocType, **values: str) -> ExtractedDocument:
    return ExtractedDocument(doc_type=doc_type, fields=[
        ExtractedField(name=k, value=v, confidence=0.99) for k, v in values.items()])  # fmt: skip


def test_the_cards_fill_exactly_the_five_identity_fields() -> None:
    out = prefill({"primary": {
        "pan_card": card(DocType.PAN_CARD, name="Rahul Rao", dob="1990-01-01", pan="HOBPR1259X"),
        "aadhaar": card(DocType.AADHAAR, name="Rahul Rao", dob="1990-01-01", aadhaar="123412341234",
                        address="1 Park Rd, Pune"),
    }})["primary"]  # fmt: skip
    assert set(out["values"]) == set(IDENTITY_FIELDS)
    assert out["values"]["aadhaar_last4"] == "1234" and out["values"]["pan"] == "HOBPR1259X"
    assert not out["notes"]
    # nothing about money, employment or contact can come out of this module
    assert not {
        "loan_amount",
        "declared_monthly_income",
        "employment_type",
        "phone",
        "email",
    } & set(out["values"])


def test_cards_that_disagree_leave_the_field_empty_with_a_note() -> None:
    out = prefill({"primary": {
        "pan_card": card(DocType.PAN_CARD, name="Rahul Rao", dob="1990-01-01", pan="HOBPR1259X"),
        "aadhaar": card(DocType.AADHAAR, name="Suresh Kumar", dob="1991-02-02", aadhaar="123412341234",
                        address="1 Park Rd, Pune"),
    }})["primary"]  # fmt: skip
    assert "full_name" not in out["values"] and "dob" not in out["values"]
    assert set(out["notes"]) == {"full_name", "dob"}
    assert out["values"]["pan"] == "HOBPR1259X"  # the other fields are unaffected


def test_a_small_spelling_difference_still_fills_the_name() -> None:
    out = prefill({"primary": {
        "pan_card": card(DocType.PAN_CARD, name="Rahul Rao", pan="HOBPR1259X"),
        "aadhaar": card(DocType.AADHAAR, name="Rahul  Raoo"),
    }})["primary"]  # fmt: skip
    assert out["values"]["full_name"] == "Rahul Rao"  # the PAN card's spelling


def test_a_low_confidence_read_is_not_offered() -> None:
    doc = ExtractedDocument(doc_type=DocType.PAN_CARD, fields=[
        ExtractedField(name="pan", value="HOBPR1259X", confidence=0.4, low_confidence=True)])  # fmt: skip
    out = prefill({"primary": {"pan_card": doc}})["primary"]
    assert "pan" not in out["values"] and "pan" in out["notes"]


def test_a_value_typed_over_is_no_longer_from_documents() -> None:
    offered = {"full_name": "Rahul Rao", "dob": "1990-01-01", "pan": "HOBPR1259X"}
    typed = {"full_name": "Rahul Rao", "dob": "1990-01-02", "pan": "hobpr1259x"}
    assert still_from_documents(offered, typed) == ["full_name", "pan"]
