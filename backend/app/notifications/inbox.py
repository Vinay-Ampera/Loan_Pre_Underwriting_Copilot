"""The in-app inbox for officers and admins: what may be said, to whom, and when.

`KINDS` is the one place that lists every notification: who gets it, the fixed title and body,
where a click goes, and the code that raises it. Review it here. Text comes from this table only;
a caller picks a kind (and, for one kind, a variant). Nothing is built from a name, a number or
free text, so a notification cannot carry personal data, a score, a band or an outcome. What it
carries besides the text: the kind, the case id (for the link) and the case number.

`notify` runs inside the caller's transaction, next to the audit row, so an event and its
notification stand or fall together. The auditor never receives one (decision 9): the insert only
matches users whose role the kind names.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.notifications import mailer
from app.notifications.check import check_notification_text

log = logging.getLogger("loan_copilot.notifications")

CASE_NO = re.compile(r"^CASE-[0-9]{4}-[0-9]{4}$")


@dataclass(frozen=True)
class Kind:
    key: str
    roles: tuple[str, ...]  # who may receive it
    who: str  # for review: the recipient in words
    when: str  # for review: the event and where in the code it is raised
    title: str
    body: str
    target: str  # where a click goes: case, issues, precedents, links, messages
    variants: tuple[tuple[str, str], ...] = ()  # (variant, title) alternatives to `title`


_ASK = "Open the case to see what changed."
KINDS: dict[str, Kind] = {
    k.key: k
    for k in (
        Kind(
            "applicant_sent",
            ("officer",),
            "the case owner",
            "the applicant pressed Send to the bank (api/public.py send_to_bank)",
            "The applicant sent their files",
            "Open the case to carry on.",
            "case",
            (("again", "The applicant sent more files"),),
        ),
        Kind(
            "applicant_request_received",
            ("officer",),
            "the link's officer",
            "a new case began from an upload link (api/public.py)",
            "A new request arrived from an upload link",
            _ASK,
            "case",
        ),
        Kind(
            "run_ready",
            ("officer",),
            "the case owner",
            "a run finished and waits for the officer (agents/graph.py decision)",
            "The check is finished and the case is ready for your decision",
            _ASK,
            "case",
        ),
        Kind(
            "run_stopped_fix",
            ("officer",),
            "the case owner",
            "a run stopped on something to fix (agents/graph.py decision)",
            "The check stopped: something needs fixing",
            _ASK,
            "case",
        ),
        Kind(
            "decision_corrected",
            ("officer",),
            "the case owner",
            "the admin corrected the decision (api/admin_cases.py override_case)",
            "The admin corrected your decision on a case",
            _ASK,
            "case",
        ),
        Kind(
            "case_reassigned",
            ("officer",),
            "the officer the case went to",
            "the admin reassigned a case (api/admin_cases.py reassign_case)",
            "A case was reassigned to you",
            _ASK,
            "case",
        ),
        Kind(
            "case_overdue",
            ("officer",),
            "the case owner",
            "a waiting case passed its decision time (workflow/sla.py check)",
            "A case is past its decision time",
            "Open the case to make your decision.",
            "case",
        ),
        Kind(
            "case_overdue_admin",
            ("admin",),
            "every active admin",
            "a waiting case is a working day past its decision time (workflow/sla.py check)",
            "A case is still waiting for its officer",
            "It passed its decision time a working day ago.",
            "case",
        ),
        Kind(
            "precedent_added",
            ("officer",),
            "the officer who proposed it",
            "the admin accepted the precedent (api/admin.py)",
            "Your precedent was added to the knowledge base",
            "",
            "case",
        ),
        Kind(
            "precedent_not_added",
            ("officer",),
            "the officer who proposed it",
            "the admin declined the precedent (api/admin.py)",
            "Your precedent was not added to the knowledge base",
            "",
            "case",
        ),
        Kind(
            "link_expiring",
            ("officer",),
            "the link's officer",
            "an open link ends within a day and the applicant still owes files "
            "(sweep_expiring_links, on read)",
            "Your upload link expires within a day",
            "Extend it if the applicant needs longer.",
            "links",
        ),
        Kind(
            "message_failed",
            ("officer",),
            "the officer who sent it",
            "a customer message could not be delivered (api/messages.py send)",
            "A customer message could not be sent",
            "Retry it from Sent items.",
            "messages",
        ),
        Kind(
            "issue_filed",
            ("admin",),
            "every active admin",
            "an officer filed a problem report (api/issues.py)",
            "A new problem report",
            "Open the Issues page to read it.",
            "issues",
        ),
        Kind(
            "precedent_pending",
            ("admin",),
            "every active admin",
            "a precedent passed the code check and waits (learning/proposal.py)",
            "A precedent is waiting for your review",
            "",
            "precedents",
        ),
        Kind(
            "precedent_held",
            ("admin",),
            "every active admin",
            "a precedent was held by the code check (learning/proposal.py)",
            "A precedent was held back by the safety check",
            "",
            "precedents",
        ),
    )
}

# The filters of the inbox: a group of kinds under a plain label; every kind is in one group.
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("applicant", "Applicant and links",
     ("applicant_sent", "applicant_request_received", "link_expiring")),
    ("runs", "Checks", ("run_ready", "run_stopped_fix")),
    ("decisions", "Decisions and cases",
     ("decision_corrected", "case_reassigned", "case_overdue", "case_overdue_admin")),
    ("precedents", "Precedents",
     ("precedent_added", "precedent_not_added", "precedent_pending", "precedent_held")),
    ("messages", "Messages and problems", ("message_failed", "issue_filed")),
)  # fmt: skip


def groups_for(role: str) -> list[dict[str, str]]:
    """The filter groups that hold at least one kind this role can receive."""
    return [{"key": k, "label": label} for k, label, kinds in GROUPS
            if any(role in KINDS[x].roles for x in kinds)]  # fmt: skip


def kinds_in(group: str) -> list[str] | None:
    return next((list(kinds) for k, _, kinds in GROUPS if k == group), None)


# Not notified, by design: every override (noise), the auditor (read-only), upload-by-upload
# arrivals (the officer is told when the applicant presses Send), and a failed run.


class NotificationContentError(ValueError):
    """A notification text broke the content check. A programming error, never user input."""


_strict = True


def configure(*, strict: bool) -> None:
    """Strict (tests, dev): a bad text raises. Not strict (production): it is logged as an error
    and the notification is dropped, so a template slip can never roll back the real event."""
    global _strict  # noqa: PLW0603
    _strict = strict


@dataclass(frozen=True)
class CaseRef:
    id: UUID | None = None
    no: str | None = None


def text_of(kind: str, variant: str | None = None) -> tuple[str, str]:
    k = KINDS[kind]
    return (dict(k.variants)[variant] if variant else k.title), k.body


def path_for(kind: str, case_id: UUID | str | None) -> str | None:
    """Where a click goes (a route of the app), never a link with a token or a name in it."""
    target = KINDS[kind].target
    if target == "case":
        return f"/cases/{case_id}" if case_id else None
    if target == "links":
        return f"/links?case={case_id}" if case_id else "/links"
    return {"issues": "/admin/issues", "precedents": "/admin/precedents", "messages": "/messages"}[
        target
    ]


def notify(
    conn: Connection, user_id: UUID | str, kind: str, case: CaseRef | None = None,
    *, variant: str | None = None,
) -> UUID | None:  # fmt: skip
    """Write one notification for one person, inside the caller's transaction."""
    k = KINDS[kind]
    title, body = text_of(kind, variant)
    bad = check_notification_text(f"{title}\n{body}")
    if bad:
        if _strict:
            raise NotificationContentError(f"{kind}: {'; '.join(bad)}")
        log.error("notification %s dropped by the content check: %s", kind, "; ".join(bad))
        return None
    ref = case.no if case and case.no and CASE_NO.match(case.no) else None
    new_id: UUID | None = conn.execute(
        text("""INSERT INTO notifications (user_id, kind, title, body, case_id, case_ref)
                SELECT u.id, :k, :t, :b, :c, :r FROM users u
                WHERE u.id = :u AND u.role = ANY(:roles)
                RETURNING id"""),
        {"u": user_id, "k": kind, "t": title, "b": body, "c": case.id if case else None,
         "r": ref, "roles": list(k.roles)},
    ).scalar_one_or_none()  # fmt: skip
    if new_id is not None:  # "you have a new notice" by email, if they want it (Part 2)
        mailer.queue_notice_email(conn, user_id)
    return new_id


def notify_admins(conn: Connection, kind: str, case: CaseRef | None = None) -> int:
    """One notification for every active admin."""
    ids = [r[0] for r in conn.execute(text("SELECT id FROM users WHERE role = 'admin' AND active"))]
    return sum(notify(conn, i, kind, case) is not None for i in ids)


def case_ref_of(conn: Connection, case_id: UUID | str) -> tuple[CaseRef, UUID] | None:
    """The case's reference and its owner (`created_by`), or None when it is gone."""
    row = conn.execute(
        text("SELECT id, case_no, created_by FROM cases WHERE id = :c"), {"c": case_id}
    ).first()
    return None if row is None else (CaseRef(row.id, row.case_no), row.created_by)


def notify_owner(
    conn: Connection, case_id: UUID | str, kind: str, *, variant: str | None = None
) -> UUID | None:  # fmt: skip
    """Notify the officer who owns the case (`cases.created_by`)."""
    found = case_ref_of(conn, case_id)
    return None if found is None else notify(conn, found[1], kind, found[0], variant=variant)


def sweep_expiring_links(conn: Connection, officer_id: UUID | str) -> int:
    """Tell the officer about each open link that ends within a day while the applicant still
    owes files. Called on read (the bell's count and the inbox list): no scheduler. An expiry time
    is claimed with one UPDATE, so it is announced once however often this runs, and an extended
    link is announced again for its new expiry."""
    claimed = conn.execute(
        text("""UPDATE upload_links l SET expiry_notified_for = l.expires_at
                WHERE l.officer_id = :u AND l.disabled_at IS NULL
                  AND l.expires_at > now() AND l.expires_at <= now() + interval '24 hours'
                  AND l.expiry_notified_for IS DISTINCT FROM l.expires_at
                  AND (l.case_id IS NULL OR EXISTS (
                        SELECT 1 FROM cases c WHERE c.id = l.case_id
                          AND c.status IN ('draft', 'uploaded', 'applicant_submitted')
                          AND (c.form_data->'applicant_sent' IS NULL
                               OR c.form_data->'more_requested' IS NOT NULL)))
                RETURNING l.case_id"""),
        {"u": officer_id},
    ).all()  # fmt: skip
    for row in claimed:
        found = case_ref_of(conn, row.case_id) if row.case_id else None
        notify(conn, officer_id, "link_expiring", found[0] if found else None)
    return len(claimed)


def row_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "title": r.title, "body": r.body, "case_id": r.case_id,
            "case_ref": r.case_ref, "created_at": r.created_at, "read_at": r.read_at,
            "path": path_for(r.kind, r.case_id)}  # fmt: skip
