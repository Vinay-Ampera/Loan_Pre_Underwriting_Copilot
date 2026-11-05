"""The intake desk's two pure steps (Stage 10, Part A). No database and no files here.

1. `assign_roles`: which person (primary or co-applicant) each accepted file belongs to.
   - The first PAN card (by upload order) is the primary applicant. A second, different PAN
     proposes the co-applicant, only if the loan type allows one. A third person stays unassigned.
   - An Aadhaar card goes to the person whose PAN card has the same date of birth and a matching
     name; with no PAN card at all, the first Aadhaar defines the primary.
   - Any other document is matched by PAN (exact), then by name (the same fuzzy matcher the
     rules use). A document naming nobody we know stays unassigned for the officer to pick.
   - A document that names nobody at all (a title deed, a bank statement without a holder)
     follows the checklist: it goes to the one person the checklist needs it from. A photograph
     has no text, so it is assigned only when there is one person.
   An officer's own choice (`fixed`) is never changed.
2. `build_inventory`: the table the officer sees. Per person: received, still missing (KYC items
   are marked essential), extra; and for the case: unassigned, unrecognised, rejected and
   duplicates that were ignored. Employment type is a claim, so until it is known the items
   that depend on it are listed apart and never counted as missing.
"""

from dataclasses import dataclass, field
from typing import Any, cast

from app.scoring import facts
from app.scoring.matching import name_match, parse_date
from app.scoring.rules import RuleSet

NAME_MIN = 85  # the same bar as CM-KYC-03
IDENTITY_NAME_FIELDS = ("name", "employee", "customer", "student", "buyer")
# one file of these covers many months, so the desk asks for one file; the assessment counts the
# months inside it and reports a shortfall itself
ONE_FILE_COVERS_MANY = {"bank_statement", "gst_returns"}
KYC_TYPES = {"pan_card", "aadhaar", "photo"}
ROLES = ("primary", "co")
# which form fields a KYC card can fill (Part B); everything else is only checked against the form
FEEDS = {
    "pan_card": ["name", "date of birth", "PAN"],
    "aadhaar": ["name", "date of birth", "Aadhaar last four", "address"],
}


@dataclass
class Item:
    """One accepted file as the assigner sees it."""

    id: str
    doc_type: str
    fields: dict[str, Any]
    order: int
    fixed: str | None = None  # the officer's choice, kept as it is


@dataclass
class Person:
    pan: str | None = None
    name: str | None = None
    dob: Any = None


def _requirements(
    rs: RuleSet, loan_type: str, employment: dict[str, str | None], details: dict[str, Any]
) -> list[Any]:
    """The checklist for these people. Employment may be unknown (None): the items that depend
    on it are then simply not part of the answer."""
    return facts.applicable_requirements(rs, loan_type, cast(Any, employment), details)


def _co_possible(co_rule: str) -> bool:
    return co_rule != "not_allowed"


def _same_person(person: Person, fields: dict[str, Any]) -> bool | None:
    """True/False when the document names someone, None when it names nobody."""
    pan = str(fields.get("pan") or "").upper() or None
    if pan and person.pan:
        return pan == person.pan
    names = [str(fields[k]) for k in IDENTITY_NAME_FIELDS if fields.get(k)]
    if not names:
        return None if not pan else False
    return any((name_match(person.name, n) or 0) >= NAME_MIN for n in names)


def _aadhaar_matches(person: Person, fields: dict[str, Any]) -> bool:
    name_ok = (name_match(person.name, str(fields.get("name") or "")) or 0) >= NAME_MIN
    a, b = parse_date(person.dob), parse_date(fields.get("dob"))
    return name_ok and (a is None or b is None or a == b)


INCOME_TYPES = {"payslip", "form16", "itr"}


def _income_owner_seat(pan: str, items: list[Item], needed_from: dict[str, set[str]]) -> str | None:
    """'co' when the income papers carrying this PAN are asked only from the co-applicant (an
    education loan: the parent earns, the student does not). Folder order says nothing about who
    is who, so this is the one clue a loan with a required co-applicant gives. Otherwise None."""

    def co_only(number: str) -> bool:
        owners: set[str] = set()
        for it in items:
            if it.doc_type in INCOME_TYPES and str(it.fields.get("pan") or "").upper() == number:
                owners |= needed_from.get(it.doc_type, set())
        return owners == {"co"}

    if not co_only(pan):
        return None
    # if every PAN on a card carries income papers, the clue does not separate the people
    others = {
        str(it.fields.get("pan") or "").upper()
        for it in items
        if it.doc_type == "pan_card" and it.fields.get("pan")
    } - {pan}
    return None if any(co_only(o) for o in others) else "co"


def assign_roles(
    items: list[Item], *, co_rule: str, needed_from: dict[str, set[str]]
) -> dict[str, str | None]:  # fmt: skip
    """`needed_from` maps a document type to the roles whose checklist asks for it. Returns
    {item id: role or None}."""
    out: dict[str, str | None] = {}
    people: dict[str, Person] = {}
    ordered = sorted(items, key=lambda i: i.order)
    for it in ordered:
        if it.fixed in ROLES:
            out[it.id] = it.fixed
    # identities fixed by the officer come first, so auto choices fill the free seats
    for it in ordered:
        if it.fixed in ROLES and it.doc_type in ("pan_card", "aadhaar"):
            p = people.setdefault(str(it.fixed), Person())
            p.pan = p.pan or (str(it.fields.get("pan")).upper() if it.fields.get("pan") else None)
            p.name = p.name or (str(it.fields["name"]) if it.fields.get("name") else None)
            p.dob = p.dob or it.fields.get("dob")

    def free_seat() -> str | None:
        for role in ROLES:
            if role not in people and (role == "primary" or _co_possible(co_rule)):
                return role
        return None

    for it in ordered:  # 1. PAN cards decide who the people are
        if it.id in out or it.doc_type != "pan_card":
            continue
        pan = str(it.fields.get("pan") or "").upper() or None
        role = next((r for r, p in people.items() if pan and p.pan == pan), None)
        if role is None and not pan:  # unreadable PAN: match by name, else leave it
            role = next((r for r, p in people.items() if _same_person(p, it.fields)), None)
        elif role is None:
            role = (_income_owner_seat(pan, ordered, needed_from) if pan else None) or free_seat()
            if role is not None and role not in people:
                people[role] = Person()
            elif role in people:
                role = free_seat()
                if role is not None:
                    people[role] = Person()
        if role is not None:
            p = people[role]
            p.pan = p.pan or pan
            p.name = p.name or (str(it.fields["name"]) if it.fields.get("name") else None)
            p.dob = p.dob or it.fields.get("dob")
        out[it.id] = role

    for it in ordered:  # 2. Aadhaar cards join a person
        if it.id in out or it.doc_type != "aadhaar":
            continue
        role = next((r for r, p in people.items() if _aadhaar_matches(p, it.fields)), None)
        if role is None and not any(p.pan for p in people.values()) and "primary" not in people:
            role = "primary"  # no PAN card anywhere: the first Aadhaar defines the primary
            people[role] = Person(name=it.fields.get("name"), dob=it.fields.get("dob"))
        out[it.id] = role

    only_one = len(people) <= 1
    for it in ordered:  # 3. everything else
        if it.id in out:
            continue
        if it.doc_type == "photo":
            out[it.id] = "primary" if only_one else None
            continue
        if it.doc_type == "unknown":
            out[it.id] = None
            continue
        matches = [r for r, p in people.items() if _same_person(p, it.fields) is True]
        names_someone = any(it.fields.get(k) for k in (*IDENTITY_NAME_FIELDS, "pan"))
        if matches:
            out[it.id] = matches[0]
        elif names_someone and people:  # it names a person who is not one of ours
            out[it.id] = None
        else:  # it names nobody, or nobody is known yet: follow the checklist
            wanted = needed_from.get(it.doc_type, set())
            seats = [r for r in ROLES if r in people] or ["primary"]
            candidates = [r for r in seats if r in wanted] or ([] if wanted else seats)
            out[it.id] = candidates[0] if len(candidates) == 1 else None
    return out


# --------------------------------------------------------------------------- the inventory
@dataclass
class Row:
    """A file row as stored (documents table), reduced to what the inventory needs."""

    id: str
    name: str
    status: str  # accepted | rejected | ignored
    doc_type: str
    classification: str | None = None
    role: str | None = None
    role_source: str = "auto"
    type_source: str = "detected"
    reject_code: str | None = None
    message: str = ""
    duplicate_of: str | None = None  # file name of the one it repeats
    duplicate_kind: str | None = None  # exact | same_document | conflict
    warnings: list[str] = field(default_factory=list)


def people_roles(co_rule: str, rows: list[Row], co_added: bool) -> list[str]:
    if co_rule == "required" or (
        co_rule == "optional" and (co_added or any(r.role == "co" for r in rows))
    ):
        return ["primary", "co"]
    return ["primary"]


def _types(req: Any) -> list[str]:
    return list(req.any_of or [req.type])


def needed_from(rs: RuleSet, loan_type: str, roles: list[str]) -> dict[str, set[str]]:
    """Document type -> roles whose checklist asks for it, with either employment type (an
    employment-dependent item is wanted from that person whichever way the claim goes)."""
    out: dict[str, set[str]] = {}
    for emp in ("salaried", "self_employed"):
        for req in _requirements(rs, loan_type, {r: emp for r in roles}, {}):
            for t in _types(req):
                out.setdefault(t, set()).update(roles if req.kyc else {req.applicant})
    return out


def _item(row: Row, feeds: bool = True) -> dict[str, Any]:
    return {
        "id": row.id, "name": row.name, "doc_type": row.doc_type, "role": row.role,
        "detected": row.classification, "type_changed": row.type_source == "officer",
        "person_changed": row.role_source == "officer", "warnings": row.warnings,
        "feeds": FEEDS.get(row.doc_type, []) if feeds else [],
    }  # fmt: skip


def build_inventory(
    rs: RuleSet, loan_type: str, rows: list[Row], *, co_rule: str,
    employment: dict[str, str | None], details: dict[str, Any], co_added: bool = False,
) -> dict[str, Any]:  # fmt: skip
    roles = people_roles(co_rule, rows, co_added)
    live = [r for r in rows if r.status == "accepted"]
    people: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    for role in roles:
        emp = employment.get(role)
        known = {role: emp}
        reqs = _requirements(rs, loan_type, known, details)
        if emp is None:  # a claim we do not know yet: accept either kind of income paper
            wanted = {
                t for e in ("salaried", "self_employed")
                for q in _requirements(rs, loan_type, {role: e}, details)  
                for t in _types(q)
            }  # fmt: skip
        else:
            wanted = {t for q in reqs for t in _types(q)}
        mine = [r for r in live if r.role == role]
        received: list[dict[str, Any]] = []
        extra: list[dict[str, Any]] = []
        for r in mine:
            if r.doc_type == "unknown":
                continue
            (received if r.doc_type in wanted else extra).append(_item(r))
        missing: list[dict[str, Any]] = []
        checklist: list[dict[str, Any]] = []  # every item of this person's list, met or not
        for req in reqs:
            if not req.kyc and req.applicant != role:
                continue
            types = _types(req)
            need = 1 if set(types) <= ONE_FILE_COVERS_MANY else req.min_count
            have = sum(1 for r in mine if r.doc_type in types)
            for rec in received:
                if rec["doc_type"] in types:
                    rec["item"] = "/".join(types)
            checklist.append({"type": "/".join(types), "needed": need, "have": have,
                              "essential": req.kyc})  # fmt: skip
            if have < need:
                missing.append({"type": "/".join(types), "types": types, "needed": need,
                                "have": have, "essential": req.kyc})  # fmt: skip
        if emp is None:
            for e in ("salaried", "self_employed"):
                base = {q.type for q in reqs}
                for q in _requirements(rs, loan_type, {role: e}, details):
                    if q.type in base or (not q.kyc and q.applicant != role):
                        continue
                    types = _types(q)
                    need = 1 if set(types) <= ONE_FILE_COVERS_MANY else q.min_count
                    have = sum(1 for r in mine if r.doc_type in types)
                    waiting.append({"role": role, "if_employment": e, "type": "/".join(types),
                                    "needed": need, "have": have})  # fmt: skip
        people.append({"role": role, "employment": emp, "received": received,
                       "missing": missing, "extra": extra, "checklist": checklist})  # fmt: skip
    unassigned = [_item(r) for r in live if r.role is None and r.doc_type != "unknown"]
    unrecognised = [_item(r, feeds=False) for r in live if r.doc_type == "unknown"]
    rejected = [{"id": r.id, "name": r.name, "code": r.reject_code, "message": r.message}
                for r in rows if r.status == "rejected"]  # fmt: skip
    duplicates = [{"id": r.id, "name": r.name, "of": r.duplicate_of, "kind": r.duplicate_kind}
                  for r in rows if r.status == "ignored"]  # fmt: skip
    conflicts = [{"id": r.id, "name": r.name, "of": r.duplicate_of}
                 for r in live if r.duplicate_kind == "conflict"]  # fmt: skip
    essential_missing = [m for p in people for m in p["missing"] if m["essential"]]
    return {
        "people": people, "unassigned": unassigned, "unrecognised": unrecognised,
        "rejected": rejected, "duplicates": duplicates, "conflicts": conflicts,
        "depends_on_employment": waiting,
        "counts": {"received": sum(len(p["received"]) for p in people),
                   "missing": sum(len(p["missing"]) for p in people),
                   "extra": sum(len(p["extra"]) for p in people),
                   "unassigned": len(unassigned), "unrecognised": len(unrecognised),
                   "rejected": len(rejected), "duplicates": len(duplicates)},  # fmt: skip
        "essential_missing": len(essential_missing),
        "complete": not any(p["missing"] for p in people) and not waiting and not unassigned,
    }  # fmt: skip
