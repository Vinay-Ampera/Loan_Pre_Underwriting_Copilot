"""Message templates, the fixed subject and the fixed fraud footer.

Every template is neutral: it only asks the customer to contact the officer. They differ in tone
(and one asks the customer to visit the branch). None states or hints at an outcome, a score, a
missing item or a reason. The footer and the contact lines are added by `compose`, never typed by
the officer, so they cannot be edited out.
"""

from dataclasses import dataclass

BANK = "Pramaan"
SUBJECT = f"{BANK}: please contact your loan officer"
LINK_SUBJECT = f"{BANK}: your secure upload link"
FOOTER = (
    "Important: this message is from an unmonitored address, so please do not reply to it. "
    "Pramaan staff will never ask you for your OTP, PIN or password, by phone, email or message. "
    "If anyone does, do not share it and tell us at once."
)
MAX_BODY = 600


@dataclass(frozen=True)
class Template:
    code: str
    label: str
    body: str


TEMPLATES: dict[str, Template] = {t.code: t for t in (
    Template("general_contact", "Please get in touch",
             "Dear customer, we would like to speak with you about your recent enquiry with "
             f"{BANK}. Please contact the officer named below at a time that suits you."),
    Template("contact_soon", "Please contact us soon",
             f"Dear customer, a member of the {BANK} team needs to speak with you about your "
             "enquiry. Please contact the officer named below as soon as you can."),
    Template("visit_branch", "Please visit the branch",
             f"Dear customer, we would like you to visit your {BANK} branch about your enquiry. "
             "Please contact the officer named below to arrange a convenient time."),
    Template("blank", "Blank (write your own)", ""),
    # Stage 10: carries only the link (added by code, never typed) and the usual footer
    Template("upload_link", "Upload link",
             f"Dear customer, to take your enquiry with {BANK} forward, please use the secure link "
             "below. It stays open for a limited time, and you can open it again to add more."),
)}  # fmt: skip


def contact_lines(
    name: str, email: str, phone: str | None, *, branch_email: str = "", branch_phone: str = ""
) -> list[str]:  # fmt: skip
    lines = [f"Officer: {name}", f"Email: {email}"]
    if phone:
        lines.append(f"Phone: {phone}")
    if branch_email:
        lines.append(f"Branch email: {branch_email}")
    if branch_phone:
        lines.append(f"Branch phone: {branch_phone}")
    return lines


def compose(body: str, contact: list[str], case_ref: str | None, link: str | None = None) -> str:
    """The text the customer receives: body, optional case reference, the upload link (only for
    the upload-link template, added by code), contact lines, footer."""
    parts = [body.strip()]
    if case_ref:
        parts.append(f"Reference: {case_ref}")
    if link:
        parts.append(f"Upload link: {link}")
    parts.append("\n".join(contact))
    parts.append(FOOTER)
    return "\n\n".join(p for p in parts if p)
