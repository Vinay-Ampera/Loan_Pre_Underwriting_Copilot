"""The content check. Runs on the server before every send, templates and blank text alike.

It scans the subject and the officer's body (the contact lines and the footer are added by code
from trusted data, so they are not scanned for what they must contain). Each hit returns a
plain-language reason shown to the officer. The patterns are deliberately blunt: a false block is
a small annoyance, a leak is not.
"""

import re

from app.notifications.templates import FOOTER, MAX_BODY


def _words(*words: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)


PERSONAL: list[tuple[str, re.Pattern[str]]] = [
    ("Contains a PAN", re.compile(r"\b[A-Za-z]{5}(?:\d{4}|\*{4})[A-Za-z]\b")),
    (
        "Contains an Aadhaar number",
        re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)|\bXXXX[ -]XXXX[ -]\d{4}\b", re.I),
    ),
    ("Contains a phone number", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    (
        "Contains a number that looks like an account number",
        re.compile(r"(?<![\d,.])\d{6,18}(?![\d,]|\.\d)"),
    ),
    ("Contains an email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

_RULES: list[tuple[str, re.Pattern[str]]] = [
    *PERSONAL,
    ("Contains a link", re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|in|org|net|co)\b", re.I)),
    (
        "Contains an amount of money",
        re.compile(r"(?:₹|\brs\.?|\binr)\s*\d|\b\d[\d,.]*\s*(?:lakhs?|crores?)\b", re.I),
    ),
    (
        "Mentions a score, a band or a rule",
        re.compile(
            r"\b(?:scored?|points?|band|rule|foir|cibil|credit rating)\b"
            r"|\b[A-Z]{2}-[A-Z]{2,6}-\d{2}\b|\d+\s*(?:/|out of)\s*100",
            re.I,
        ),
    ),
    (
        "Mentions a result of the assessment",
        _words(
            "approve[ds]?",
            "approval",
            "reject(?:ed|ion)?",
            "declin(?:e|ed)",
            "denied",
            "sanction(?:ed)?",
            "eligible",
            "ineligible",
            "not eligible",
            "recommend(?:ed|ation)?",
            "refer(?:red|ral)?",
            "unsuccessful",
            "shortlisted",
            "disbursed?",
        ),
    ),
    (
        "Mentions a missing item or a problem with the application",
        _words(
            "missing",
            "incomplete",
            "mismatch(?:ed)?",
            "discrepanc(?:y|ies)",
            "unverified",
            "pending documents?",
            "payslips?",
            "bank statements?",
            "itr",
            "form 16",
            "salary slips?",
            "documents?",
        ),
    ),
    (
        "Asks for an OTP, PIN, password or card detail",
        re.compile(
            r"\botp\b|one[- ]time (?:password|pin|code)|\bpin\b(?!\s*code)|\bpasswords?\b"
            r"|\bcvv\b|\bcard (?:number|details)\b|\bpasscode\b",
            re.I,
        ),
    ),
]


def check_message(
    subject: str, body: str, *, final_text: str, names: list[str] | None = None
) -> list[str]:  # fmt: skip
    """Reasons the message must not be sent (empty list = clean)."""
    reasons: list[str] = []
    text = f"{subject}\n{body}"
    if not body.strip():
        reasons.append("The message is empty")
    if len(body) > MAX_BODY:
        reasons.append(f"The message is longer than {MAX_BODY} characters")
    for reason, pattern in _RULES:
        if pattern.search(text):
            reasons.append(reason)
    for name in names or []:
        for token in re.findall(r"[A-Za-z]{3,}", name):
            if re.search(rf"\b{re.escape(token)}\b", text, re.I):
                reasons.append("Contains the customer's name")
                break
        else:
            continue
        break
    if FOOTER not in final_text:
        reasons.append("The fraud warning is missing")
    return list(dict.fromkeys(reasons))


# Issue reports (officer to admin): the personal-data patterns only; ordinary words are fine.
def check_issue_text(text: str) -> list[str]:
    return [reason for reason, pattern in PERSONAL if pattern.search(text)]


_URL = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.I)


def check_link_line(final_text: str, allowed_url: str | None) -> list[str]:
    """The Upload link message may carry exactly one link, the case's own upload link, and
    nothing else may look like a link. Every other message may carry none."""
    found = _URL.findall(final_text)
    if allowed_url is None:
        return ["Contains a link"] if found else []
    return [] if found == [allowed_url] else ["Contains a link other than the upload link"]
