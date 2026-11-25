"""Real email (Notifications Part 2). The guard: only allow-listed addresses ever receive email;
others go to the demo inbox or nowhere. The SMTP sender (a fake SMTP client: no network). The
start-up check of the settings. The staff email queue: written in the event's transaction, one
notice email per person per gap, the person's choice respected, never to the auditor, never a
password; delivered after the commit with retries, every outcome audited with a masked address.
Customer messages record how they went out."""

import asyncio
import json
import smtplib
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings
from app.db.migrate import alembic_config
from app.notifications import mailer
from app.notifications.check import check_notification_text
from app.notifications.inbox import notify
from app.notifications.sender import (
    ConsoleSender,
    GuardedSender,
    NotAllowedError,
    Outgoing,
    SendError,
    SmtpSender,
    build_sender,
    check_email_settings,
)
from tests import test_auditor
from tests.test_api import login
from tests.test_notifications import done_case, draft

client = test_auditor.client  # the same app, database and users as the auditor tests
engine = test_auditor.engine
V1 = "/api/v1"
KEY = "re_TEST_SECRET_KEY_must_never_show"
ME = "me@inbox.example"


class Recording:
    """An inner sender that records what it was asked to deliver."""

    def __init__(self, fail: int = 0) -> None:
        self.sent: list[Outgoing] = []
        self.fail = fail  # fail this many times first

    def send(self, message: Outgoing) -> str:
        if self.fail:
            self.fail -= 1
            raise SendError("The mail server could not be reached. Try again later.")
        self.sent.append(message)
        return "sent"


def smtp_settings(**over: Any) -> Settings:
    base: dict[str, Any] = dict(
        _env_file=None, notification_sender="smtp", smtp_host="smtp.resend.com", smtp_port=465,
        smtp_security="ssl", smtp_username="resend", smtp_password=SecretStr(KEY),
        email_from="Pramaan <onboarding@resend.dev>", email_allowlist=f"{ME},delivered@resend.dev",
        email_redirect_to=ME,
    )  # fmt: skip
    return Settings(**{**base, **over})


MSG = Outgoing("m1", "customer@example.test", "Please call us", "Hello.\nCall the branch.")


# --------------------------------------------------------------------------- the guard
def test_an_allow_listed_address_gets_the_message_as_it_is() -> None:
    inner = Recording()
    g = GuardedSender(inner, {ME}, None)
    assert g.send(Outgoing("m", "Me@Inbox.Example", "S", "T")) == "sent"  # capitals do not matter
    assert inner.sent[0].recipient == "Me@Inbox.Example" and inner.sent[0].subject == "S"


def test_any_other_address_goes_to_the_demo_inbox_with_the_real_one_masked() -> None:
    inner = Recording()
    assert GuardedSender(inner, {ME}, ME).send(MSG) == "redirected"
    (out,) = inner.sent
    assert out.recipient == ME and out.text == MSG.text
    assert out.subject == "[demo, for ****@example.test] Please call us"
    assert "customer@" not in out.subject + out.recipient


def test_with_no_redirect_it_is_printed_and_refused_never_sent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    inner = Recording()
    with pytest.raises(NotAllowedError, match="allow-list"):
        GuardedSender(inner, {ME}, None).send(MSG)
    assert inner.sent == [] and "Please call us" in capsys.readouterr().out
    assert issubclass(NotAllowedError, SendError)  # a customer message is then marked failed


# --------------------------------------------------------------------------- the settings
def test_console_needs_nothing_and_smtp_builds_a_guarded_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a library imported by the tests (LiteLLM) loads the developer's .env into the process
    # environment, so a machine set up for real email would otherwise see smtp here
    monkeypatch.delenv("NOTIFICATION_SENDER", raising=False)
    assert isinstance(build_sender(Settings(_env_file=None)), ConsoleSender)  # type: ignore[call-arg]
    sender = build_sender(smtp_settings())
    assert isinstance(sender, GuardedSender) and sender.redirect == ME
    assert sender.allow == {ME, "delivered@resend.dev"} and isinstance(sender.inner, SmtpSender)


@pytest.mark.parametrize(
    ("over", "said"),
    [
        ({"notification_sender": "pigeon"}, "Unknown NOTIFICATION_SENDER"),
        ({"smtp_host": ""}, "SMTP_HOST is empty"),
        ({"smtp_security": "tls"}, "SMTP_SECURITY"),
        ({"smtp_password": None}, "SMTP_PASSWORD is empty"),
        ({"email_from": "Pramaan"}, "EMAIL_FROM"),
        ({"email_allowlist": "not-an-address"}, "EMAIL_ALLOWLIST"),
        ({"email_redirect_to": "other@inbox.example"}, "EMAIL_REDIRECT_TO must also be on"),
    ],
)
def test_a_wrong_email_setup_refuses_to_start_and_names_the_variable_not_the_key(
    over: dict[str, Any], said: str
) -> None:  # fmt: skip
    with pytest.raises(RuntimeError, match=said) as err:
        check_email_settings(smtp_settings(**over))
    assert KEY not in str(err.value)


def test_an_empty_allow_list_is_allowed_and_then_nothing_is_ever_delivered() -> None:
    sender = build_sender(smtp_settings(email_allowlist="", email_redirect_to=""))
    with pytest.raises(NotAllowedError):
        sender.send(Outgoing("m", ME, "S", "T"))


# --------------------------------------------------------------------------- the SMTP sender
class FakeSMTP:
    """Stands in for smtplib.SMTP and SMTP_SSL."""

    made: list["FakeSMTP"] = []
    error: Exception | None = None

    def __init__(self, host: str, port: int, **kw: Any) -> None:
        self.host, self.port, self.kw = host, port, kw
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSMTP.made.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *a: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kw: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}:{password == KEY}")
        if FakeSMTP.error:
            raise FakeSMTP.error

    def send_message(self, m: Any) -> None:
        self.sent.append(m)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[FakeSMTP]]:
    FakeSMTP.made, FakeSMTP.error = [], None
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    yield FakeSMTP


def test_smtp_over_ssl_signs_in_and_sends_a_plain_no_reply_email(fake_smtp: type[FakeSMTP]) -> None:
    assert (
        SmtpSender(smtp_settings()).send(Outgoing("m", ME, "Subject here", "Body here")) == "sent"
    )
    (c,) = fake_smtp.made
    assert (c.host, c.port, c.kw["timeout"]) == ("smtp.resend.com", 465, 15)
    assert c.calls == ["login:resend:True", "quit"]  # the key is the password, as Resend wants
    (m,) = c.sent
    assert m["From"] == "Pramaan <onboarding@resend.dev>" and m["To"] == ME
    assert m["Subject"] == "Subject here" and m["Auto-Submitted"] == "auto-generated"
    assert m.get_content().strip() == "Body here" and KEY not in m.as_string()


def test_starttls_and_a_server_without_sign_in(fake_smtp: type[FakeSMTP]) -> None:
    SmtpSender(smtp_settings(smtp_security="starttls", smtp_port=587)).send(MSG)
    assert fake_smtp.made[-1].calls[:2] == ["starttls", "login:resend:True"]
    SmtpSender(smtp_settings(smtp_security="none", smtp_port=1025, smtp_username="")).send(MSG)
    assert fake_smtp.made[-1].calls == ["quit"]  # Mailpit: no TLS, no sign-in


@pytest.mark.parametrize(
    ("error", "said"),
    [
        (smtplib.SMTPAuthenticationError(535, b"bad key " + KEY.encode()), "refused the sign-in"),
        (smtplib.SMTPRecipientsRefused({}), "refused the recipient"),
        (smtplib.SMTPResponseException(554, b"no"), r"refused the message \(554\)"),
        (OSError("network down"), "could not be reached"),
    ],
)
def test_a_server_problem_becomes_a_plain_send_error_without_the_key(
    fake_smtp: type[FakeSMTP], error: Exception, said: str
) -> None:  # fmt: skip
    fake_smtp.error = error
    with pytest.raises(SendError, match=said) as err:
        SmtpSender(smtp_settings()).send(MSG)
    assert KEY not in str(err.value) and err.value.__cause__ is None  # nothing chained to leak


# --------------------------------------------------------------------------- the email texts
def test_every_staff_email_is_fixed_text_with_a_sign_in_link_and_never_a_password() -> None:
    mailer.configure(base_url="https://pramaan.example/", gap_minutes=30)
    try:
        for kind in mailer.MAILS:
            subject, body = mailer.compose(kind)
            assert check_notification_text(subject) == []
            assert "https://pramaan.example/login" in body and mailer.FOOTER in body
            assert "never sent by email" in body
            assert not any(ch.isdigit() for ch in subject)
    finally:
        mailer.configure(base_url="http://localhost:5173", gap_minutes=30)


# --------------------------------------------------------------------------- the queue (database)
def uid(engine: Engine, who: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("SELECT id FROM users WHERE email = :e"),
                             {"e": f"{who}@example.test"}).scalar_one())  # fmt: skip


def queued(engine: Engine, kind: str | None = None) -> list[Any]:
    with engine.connect() as c:
        return list(c.execute(
            text("""SELECT * FROM email_outbox WHERE CAST(:k AS text) IS NULL OR kind = :k
                    ORDER BY created_at, id"""), {"k": kind}))  # fmt: skip


@pytest.mark.db
def test_a_notice_queues_one_email_per_person_per_gap_and_respects_the_choice(
    engine: Engine,
) -> None:
    asha, ben, ada, aud = (uid(engine, w) for w in ("asha", "ben", "ada", "aud"))
    with engine.begin() as c:
        c.execute(text("UPDATE users SET notice_emails = false WHERE id = :u"), {"u": ben})
        for _ in range(3):
            notify(c, asha, "run_ready")  # three notices, one email
        notify(c, ben, "run_ready")  # Ben turned them off
        notify(c, ada, "issue_filed")
        notify(c, aud, "run_ready")  # never the auditor (no notice, no email)
    rows = queued(engine, "notice")
    assert sorted(r.recipient for r in rows) == ["ada@example.test", "asha@example.test"]
    assert all(r.status == "queued" for r in rows)
    with engine.begin() as c:  # after the gap, the next notice may email again
        c.execute(text("UPDATE email_outbox SET created_at = now() - interval '31 minutes'"))
        notify(c, asha, "case_reassigned")
    assert len(queued(engine, "notice")) == 3


@pytest.mark.db
def test_a_rolled_back_event_queues_no_email(engine: Engine) -> None:
    with engine.connect() as c, c.begin() as tx:
        notify(c, uid(engine, "asha"), "run_ready")
        tx.rollback()
    assert queued(engine) == []


@pytest.mark.db
def test_a_disabled_person_gets_no_email(engine: Engine) -> None:
    asha = uid(engine, "asha")
    with engine.begin() as c:
        c.execute(text("UPDATE users SET active = false WHERE id = :u"), {"u": asha})
        notify(c, asha, "run_ready")
        assert mailer.queue_account_email(c, asha, "password_reset") is False
    assert queued(engine) == []


@pytest.mark.db
def test_delivery_sends_redirects_holds_and_audits_with_a_masked_address(
    engine: Engine,
) -> None:  # fmt: skip
    asha, ben = uid(engine, "asha"), uid(engine, "ben")
    with engine.begin() as c:
        notify(c, asha, "run_ready")
        notify(c, ben, "run_ready")
    inner = Recording()
    # Asha's address is allowed; Ben's goes to the demo inbox
    assert mailer.deliver_pending(engine, GuardedSender(inner, {"asha@example.test"}, ME)) == 2
    assert {r.recipient: r.status for r in queued(engine)} == {
        "asha@example.test": "sent", "ben@example.test": "redirected"}  # fmt: skip
    assert [m.recipient for m in inner.sent] == ["asha@example.test", ME]
    assert mailer.deliver_pending(engine, GuardedSender(inner, set(), ME)) == 0  # nothing twice
    with engine.connect() as c:
        log = c.execute(
            text("SELECT action, after FROM audit_log WHERE action LIKE 'email_%'")
        ).all()
    assert [a for a, _ in log] == ["email_sent", "email_sent"]
    assert {a["to"] for _, a in log} == {"****@example.test"}
    assert {a["delivery"] for _, a in log} == {"sent", "redirected"}
    assert "asha@" not in json.dumps([a for _, a in log])

    with engine.begin() as c:  # no redirect: held, printed, never sent
        c.execute(text("UPDATE email_outbox SET created_at = now() - interval '1 hour'"))
        notify(c, asha, "case_reassigned")
    mailer.deliver_pending(engine, GuardedSender(inner, set(), None))
    assert queued(engine)[-1].status == "held" and len(inner.sent) == 2


class Exploding:
    """An inner sender that fails in a way no sender expects, on one address only."""

    def __init__(self, bad: str) -> None:
        self.bad = bad
        self.sent: list[str] = []

    def send(self, message: Outgoing) -> str:
        if message.recipient == self.bad:
            raise ValueError("boom")
        self.sent.append(message.recipient)
        return "sent"


@pytest.mark.db
def test_one_bad_email_never_undoes_the_others_so_nothing_is_sent_twice(engine: Engine) -> None:
    asha, ben = uid(engine, "asha"), uid(engine, "ben")
    with engine.begin() as c:
        notify(c, asha, "run_ready")
        notify(c, ben, "run_ready")
    inner = Exploding("asha@example.test")
    sender = GuardedSender(inner, {"asha@example.test", "ben@example.test"}, None)
    assert mailer.deliver_pending(engine, sender) == 2
    rows = {r.recipient: r for r in queued(engine)}
    assert rows["ben@example.test"].status == "sent"
    assert rows["asha@example.test"].status == "queued"
    assert rows["asha@example.test"].last_error == "unexpected error (ValueError)"
    with engine.begin() as c:
        c.execute(text("UPDATE email_outbox SET next_attempt_at = now()"))
    mailer.deliver_pending(engine, sender)
    assert inner.sent == ["ben@example.test"]  # Ben's email went once, not again


def test_the_smtp_sender_refuses_a_bad_address_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    def no_connection(*a: Any, **k: Any) -> Any:
        raise AssertionError("no connection may be opened for a bad address")

    monkeypatch.setattr(smtplib, "SMTP_SSL", no_connection)
    sender = SmtpSender(smtp_settings())
    for bad in ("a@b.com\r\nBcc: x@y.com", "a@b.com, x@y.com", "not-an-address"):
        with pytest.raises(SendError, match="recipient address is not valid"):
            sender.send(Outgoing("m1", bad, "Subject", "Body"))


@pytest.mark.db
def test_a_failing_server_is_tried_three_times_then_marked_failed_once(engine: Engine) -> None:
    with engine.begin() as c:
        notify(c, uid(engine, "asha"), "run_ready")
    inner = Recording(fail=5)
    sender = GuardedSender(inner, {"asha@example.test"}, None)
    for expected, wait in (("queued", 1), ("queued", 5), ("failed", None)):
        assert mailer.deliver_pending(engine, sender) == 1
        (row,) = queued(engine)
        assert row.status == expected
        if wait is None:
            continue
        # the next try waits: the very next pass of the loop leaves the row alone
        assert mailer.deliver_pending(engine, sender) == 0
        with engine.begin() as c:
            minutes = c.execute(text(
                "SELECT round(extract(epoch FROM next_attempt_at - now()) / 60) FROM email_outbox"
            )).scalar_one()  # fmt: skip
            assert minutes == wait
            c.execute(text("UPDATE email_outbox SET next_attempt_at = now()"))
    assert row.attempts == 3 and "could not be reached" in row.last_error
    mailer.deliver_pending(engine, sender)  # a failed row is not tried again
    with engine.connect() as c:
        actions = [
            r[0]
            for r in c.execute(text("SELECT action FROM audit_log WHERE action LIKE 'email_%'"))
        ]
    assert actions == ["email_failed"] and inner.sent == []


@pytest.mark.db
def test_the_worker_loop_sends_what_is_queued_and_survives_an_error(engine: Engine) -> None:
    with engine.begin() as c:
        notify(c, uid(engine, "asha"), "run_ready")
    inner = Recording()

    async def scenario() -> None:
        task = asyncio.create_task(mailer.run_worker(engine, GuardedSender(inner, set(), ME), 0))
        for _ in range(200):
            await asyncio.sleep(0.02)
            if inner.sent:
                break
        task.cancel()

    asyncio.run(scenario())
    assert len(inner.sent) == 1 and inner.sent[0].recipient == ME


# --------------------------------------------------------------------------- accounts and choice
@pytest.mark.db
def test_a_new_account_and_a_reset_are_emailed_without_the_password(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    ada = login(client, "ada")
    made = client.post(f"{V1}/admin/users", headers=ada, json={
        "name": "Cara Officer", "email": "cara@example.test", "role": "officer"}).json()  # fmt: skip
    (created,) = queued(engine, "account_created")
    assert created.recipient == "cara@example.test" and created.status == "queued"
    assert made["temporary_password"] not in created.body + created.subject
    reset = client.post(f"{V1}/admin/users/{made['id']}/reset-password", headers=ada).json()
    (again,) = queued(engine, "password_reset")
    assert reset["temporary_password"] not in again.body and "Ask the admin" in again.body
    with engine.connect() as c:  # notice emails start as STAFF_EMAILS_DEFAULT says (on)
        assert c.execute(text("SELECT notice_emails FROM users WHERE id = :i"),
                         {"i": made["id"]}).scalar_one() is True  # fmt: skip


@pytest.mark.db
def test_each_person_turns_notice_emails_off_and_on_and_the_auditor_cannot(
    client: TestClient, engine: Engine
) -> None:  # fmt: skip
    asha, aud = login(client, "asha"), login(client, "aud")
    assert client.get(f"{V1}/me/preferences", headers=asha).json() == {"notice_emails": True}
    off = client.put(f"{V1}/me/preferences", headers=asha, json={"notice_emails": False})
    assert off.json() == {"notice_emails": False}
    client.put(f"{V1}/me/preferences", headers=asha, json={"notice_emails": False})  # no change
    with engine.begin() as c:
        notify(c, uid(engine, "asha"), "run_ready")
    assert queued(engine) == []  # the notice is in the inbox, no email
    with engine.connect() as c:
        changes = c.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'notice_emails_changed'")
        )
        assert changes.scalar_one() == 1
    for method in ("GET", "PUT"):
        r = client.request(
            method, f"{V1}/me/preferences", headers=aud, json={"notice_emails": True}
        )
        assert r.status_code == 403
    assert client.put(f"{V1}/me/preferences", headers=asha, json={"x": 1}).status_code == 422


# --------------------------------------------------------------------------- customer messages
@pytest.mark.db
@pytest.mark.parametrize(
    ("allow", "redirect", "status", "delivery"),
    [
        ({"customer@example.test"}, None, 200, "sent"),
        (set(), ME, 200, "redirected"),
        (set(), None, 502, None),
    ],
)
def test_a_customer_message_records_how_it_went_out(
    client: TestClient, engine: Engine, allow: set[str], redirect: str | None, status: int,
    delivery: str | None,
) -> None:  # fmt: skip
    inner = Recording()
    client.app.state.sender = GuardedSender(inner, allow, redirect)  # type: ignore[attr-defined]
    case_id, h = done_case(client, engine)
    m = draft(client, h, case_id).json()
    r = client.post(f"{V1}/messages/{m['id']}/send", headers=h, json={"second_click": True})
    assert r.status_code == status, r.text
    got = client.get(f"{V1}/messages/{m['id']}", headers=h).json()
    assert got["delivery"] == delivery
    with engine.connect() as c:
        audit = c.execute(text("SELECT action, after FROM audit_log WHERE entity = 'message' "
                               "AND action IN ('message_sent', 'message_failed')")).one()  # fmt: skip
    if delivery:
        assert audit.action == "message_sent" and audit.after["delivery"] == delivery
        assert len(inner.sent) == 1
    else:  # not allowed and no redirect: failed, printed, the officer is told why
        assert audit.action == "message_failed" and got["status"] == "failed"
        assert "allow-list" in got["error"] and inner.sent == []


@pytest.mark.db
def test_the_console_sender_records_printed(client: TestClient, engine: Engine) -> None:
    client.app.state.sender = ConsoleSender()  # type: ignore[attr-defined]
    case_id, h = done_case(client, engine)
    m = draft(client, h, case_id).json()
    client.post(f"{V1}/messages/{m['id']}/send", headers=h, json={"second_click": True})
    assert client.get(f"{V1}/messages/{m['id']}", headers=h).json()["delivery"] == "printed"


# --------------------------------------------------------------------------- the migration
@pytest.mark.db
def test_the_email_migration_applies_rolls_back_and_applies_again(clean_db_url: str) -> None:
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "head")
    eng = create_engine(clean_db_url)

    def shape() -> tuple[int, int, int]:
        with eng.connect() as c:
            one = c.execute(text("SELECT count(*) FROM pg_tables WHERE tablename = 'email_outbox'"))
            cols = c.execute(text("""SELECT count(*) FROM information_schema.columns
                WHERE (table_name, column_name) IN (('users', 'notice_emails'),
                                                    ('outbox', 'delivery'))"""))  # fmt: skip
            return int(one.scalar_one()), int(cols.scalar_one()), 0

    assert shape()[:2] == (1, 2)
    command.downgrade(cfg, "0019")
    assert shape()[:2] == (0, 0)
    command.upgrade(cfg, "head")
    assert shape()[:2] == (1, 2)
    eng.dispose()


# --------------------------------------------------------------------------- the manual check
def test_the_email_check_command_uses_the_guard_and_never_prints_the_key(
    fake_smtp: type[FakeSMTP], capsys: pytest.CaptureFixture[str]
) -> None:  # fmt: skip
    from app.notifications import email_check  # noqa: PLC0415

    assert email_check.main([], smtp_settings()) == 0
    out = capsys.readouterr().out
    assert "sent by email" in out and "****@inbox.example" in out and KEY not in out
    assert fake_smtp.made[-1].sent[0]["To"] == ME
    # an address off the list goes to the demo inbox, never to itself
    assert email_check.main(["--to", "someone@else.example"], smtp_settings()) == 0
    assert "demo inbox" in capsys.readouterr().out and fake_smtp.made[-1].sent[0]["To"] == ME
    fake_smtp.error = smtplib.SMTPAuthenticationError(535, KEY.encode())
    assert email_check.main([], smtp_settings()) == 1
    out = capsys.readouterr().out
    assert "refused the sign-in" in out and KEY not in out
    assert email_check.main([], smtp_settings(email_allowlist="", email_redirect_to="")) == 2
