"""2-step verification at sign-in (SECURITY.md 4h): admins and the auditor give a 6-digit code from
an authenticator app after the password, set it up at their first sign-in, can use a recovery code
once each, and an admin resets another person's 2-step with a reason and a second click. Officers
are not asked. The phone's clock is replaced by a test clock, so every code is known."""

import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from alembic import command
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text

from app.api import auth, mfa, users_cli
from app.api.main import create_app
from app.api.security import MFA_AUDIENCE, hash_password
from app.core.config import Settings
from app.db.migrate import alembic_config
from app.rag.retrieve import PolicyRetriever
from tests.rag_helpers import fake_rerank, fake_vector

PASSWORD = "correct horse battery"
SECRET = "test-secret-" + "x" * 32
V1 = "/api/v1"
START = 1_800_000_000.0  # a fixed moment for the test clock


# --------------------------------------------------------------------------- the code itself
def test_codes_match_the_rfc_6238_test_vectors() -> None:
    # RFC 6238 appendix B, SHA-1 key "12345678901234567890"; the last six of each 8-digit value
    key = base64.b32encode(b"12345678901234567890").decode()
    for t, expected in ((59, "287082"), (1111111109, "081804"), (1234567890, "005924"),
                        (2000000000, "279037")):  # fmt: skip
        assert mfa.code_at(key, mfa.current_step(t)) == expected


def test_a_code_from_30_seconds_either_side_counts_but_only_once() -> None:
    key = mfa.new_secret()
    assert len(key) == 32
    here = mfa.current_step(START)
    for step in (here - 1, here, here + 1):
        assert mfa.matching_step(key, mfa.code_at(key, step), None, START) == step
    assert mfa.matching_step(key, mfa.code_at(key, here + 2), None, START) is None
    assert mfa.matching_step(key, mfa.code_at(key, here), here, START) is None  # already used
    assert mfa.matching_step(key, mfa.code_at(key, here + 1), here, START) == here + 1
    assert mfa.matching_step(key, "12345", None, START) is None
    assert mfa.matching_step(key, "abcdef", None, START) is None


def test_setup_gives_a_qr_code_and_the_key_for_typing_in() -> None:
    key = mfa.new_secret()
    shown = mfa.setup_payload(key, "ada@example.test")
    assert shown["qr"].startswith("data:image/svg+xml")
    assert shown["key"].replace(" ", "") == key and shown["issuer"] == "Pramaan"
    assert (shown["digits"], shown["period"]) == (6, 30)


def test_the_stored_key_is_sealed_and_a_new_jwt_secret_cannot_open_it() -> None:
    one = Settings(_env_file=None, jwt_secret=SecretStr(SECRET))  # type: ignore[call-arg]
    two = Settings(_env_file=None, jwt_secret=SecretStr(SECRET + "y"))  # type: ignore[call-arg]
    key = mfa.new_secret()
    sealed = mfa.seal(one, key)
    assert key not in sealed and mfa.unseal(one, sealed) == key
    assert mfa.unseal(two, sealed) is None and mfa.unseal(one, None) is None


def test_recovery_codes_are_easy_to_read_and_stored_as_hashes() -> None:
    codes = mfa.new_recovery_codes()
    assert len(codes) == 8 and len(set(codes)) == 8
    for c in codes:
        assert len(c) == 11 and c[5] == "-" and mfa.looks_like_recovery(mfa.clean_code(c))
        assert not set(c) & set("01ilo")
    assert mfa.hash_recovery(codes[0]) == mfa.hash_recovery(codes[0].upper().replace("-", " "))


def test_who_is_asked_for_a_code() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.mfa_role_set() == {"admin", "auditor"}  # the default: officers are not asked
    row = SimpleNamespace(role="officer", mfa_enabled_at=None)
    assert not auth.needs_two_step(s, row)
    assert auth.needs_two_step(s, SimpleNamespace(role="admin", mfa_enabled_at=None))
    # an account that has 2-step set up is always asked, whatever the list says
    off = Settings(_env_file=None, mfa_roles="")  # type: ignore[call-arg]
    assert auth.needs_two_step(
        off, SimpleNamespace(role="officer", mfa_enabled_at=datetime.now(UTC))
    )


# --------------------------------------------------------------------------- over HTTP


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The time the codes are made and checked at. Move it with `clock[0] += 30`."""
    now = [START]
    monkeypatch.setattr(mfa, "time", SimpleNamespace(time=lambda: now[0]))
    return now


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        for name, role in (("Asha Officer", "officer"), ("Ada Admin", "admin"),
                           ("Ari Admin", "admin"), ("Aud Auditor", "auditor")):  # fmt: skip
            conn.execute(
                text("INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)"),
                {"n": name, "e": f"{name.split()[0].lower()}@example.test",
                 "h": hash_password(PASSWORD), "r": role},
            )  # fmt: skip
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine, tmp_path: Path, clock: list[float]) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr(SECRET),
        upload_dir=tmp_path / "uploads",
        login_max_failures=3,
    )  # fmt: skip  (MFA_ROLES stays at its default: admin and auditor)
    app = create_app(
        settings, engine=engine, saver=InMemorySaver(), use_llm=False,
        ctx_kwargs={"retriever_factory": lambda c: PolicyRetriever(
            c, embed=fake_vector, rerank_fn=fake_rerank)},
    )  # fmt: skip
    with TestClient(app) as c:
        yield c


def password_step(client: TestClient, who: str, password: str = PASSWORD) -> Any:
    return client.post(
        f"{V1}/auth/login", json={"email": f"{who}@example.test", "password": password}
    )


def code_step(client: TestClient, token: str, code: str) -> Any:
    return client.post(f"{V1}/auth/mfa/verify", json={"mfa_token": token, "code": code})


def now_code(key: str, clock: list[float]) -> str:
    return mfa.code_at(key, mfa.current_step(clock[0]))


def set_up(
    client: TestClient, who: str, clock: list[float]
) -> tuple[str, list[str], dict[str, str]]:
    """First sign-in: scan (read the key), give the first code. Returns key, recovery codes, headers."""
    first = password_step(client, who).json()
    assert first["mfa"] == "setup", first
    key = first["setup"]["key"].replace(" ", "")
    r = code_step(client, first["mfa_token"], now_code(key, clock))
    assert r.status_code == 200, r.text
    return key, r.json()["recovery_codes"], {"Authorization": f"Bearer {r.json()['access_token']}"}


def actions(engine: Engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("SELECT action FROM audit_log"))]  # ids are uuids


def user_row(engine: Engine, who: str) -> Any:
    with engine.connect() as c:
        return c.execute(
            text("SELECT * FROM users WHERE email = :e"), {"e": f"{who}@example.test"}
        ).one()


@pytest.mark.db
def test_an_officer_signs_in_with_the_password_alone(client: TestClient) -> None:
    r = password_step(client, "asha")
    assert r.status_code == 200 and "access_token" in r.json() and "mfa" not in r.json()


@pytest.mark.db
def test_an_admin_gets_no_session_from_the_password_alone(
    client: TestClient, engine: Engine
) -> None:
    r = password_step(client, "ada")
    body = r.json()
    assert r.status_code == 200 and body["mfa"] == "setup" and "access_token" not in body
    assert "lc_refresh" not in r.headers.get("set-cookie", "")
    # the 2-step token is not an access token
    me = client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {body['mfa_token']}"})
    assert me.status_code == 401
    assert actions(engine) == ["two_step_asked"]  # no "login": there is no session yet
    # the key waits, sealed, for the first code
    row = user_row(engine, "ada")
    assert (
        row.mfa_pending_secret
        and body["setup"]["key"].replace(" ", "") not in row.mfa_pending_secret
    )
    assert row.mfa_enabled_at is None


@pytest.mark.db
def test_first_sign_in_sets_up_2_step_and_shows_recovery_codes_once(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    first = password_step(client, "ada").json()
    key = first["setup"]["key"].replace(" ", "")
    wrong = code_step(
        client, first["mfa_token"], "000000" if now_code(key, clock) != "000000" else "111111"
    )
    assert wrong.status_code == 401 and "not right" in wrong.json()["detail"]
    assert user_row(engine, "ada").failed_logins == 1
    r = code_step(client, first["mfa_token"], now_code(key, clock))
    assert r.status_code == 200 and "access_token" in r.json()
    assert "lc_refresh" in r.headers["set-cookie"]
    codes = r.json()["recovery_codes"]
    assert len(codes) == 8
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{V1}/auth/me", headers=h).json()["role"] == "admin"
    row = user_row(engine, "ada")
    assert row.mfa_enabled_at and row.mfa_pending_secret is None and row.failed_logins == 0
    assert key not in (row.mfa_secret or "")
    with engine.connect() as c:
        stored = [x[0] for x in c.execute(text("SELECT code_hash FROM user_recovery_codes"))]
    assert len(stored) == 8 and not set(codes) & set(stored)  # hashes only
    assert {"two_step_failed", "two_step_enabled", "login"} <= set(actions(engine))
    with engine.connect() as c:
        after = c.execute(text("SELECT after FROM audit_log WHERE action = 'login'")).scalar_one()
    assert after == {"two_step": "setup"}
    assert not any(c in json.dumps(after) for c in codes)
    # the next sign-in asks for a code and shows no QR code
    again = password_step(client, "ada").json()
    assert again["mfa"] == "code" and "setup" not in again


@pytest.mark.db
def test_a_code_works_once_and_the_next_one_signs_in(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    key, _, _ = set_up(client, "ada", clock)
    token = password_step(client, "ada").json()["mfa_token"]
    assert code_step(client, token, now_code(key, clock)).status_code == 401  # used at setup
    clock[0] += 30
    r = code_step(client, token, now_code(key, clock))
    assert r.status_code == 200 and "recovery_codes" not in r.json()
    with engine.connect() as c:
        logins = [
            x[0] for x in c.execute(text("SELECT after FROM audit_log WHERE action = 'login'"))
        ]
    assert sorted(x["two_step"] for x in logins) == ["app", "setup"]


@pytest.mark.db
def test_a_recovery_code_signs_in_once(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    _, codes, _ = set_up(client, "ada", clock)
    token = password_step(client, "ada").json()["mfa_token"]
    r = code_step(client, token, codes[0].upper().replace("-", " "))  # typed loosely
    assert r.status_code == 200 and r.json()["recovery_codes_left"] == 7
    assert "two_step_recovery_used" in actions(engine)
    token = password_step(client, "ada").json()["mfa_token"]
    assert code_step(client, token, codes[0]).status_code == 401  # spent
    assert code_step(client, token, codes[1]).json()["recovery_codes_left"] == 6


@pytest.mark.db
def test_wrong_codes_lock_the_account_like_wrong_passwords(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    key, _, _ = set_up(client, "ada", clock)
    clock[0] += 30
    token = password_step(client, "ada").json()["mfa_token"]
    good = now_code(key, clock)
    bad = "000000" if good != "000000" else "111111"
    assert code_step(client, token, bad).status_code == 401
    assert code_step(client, token, bad).status_code == 401
    assert code_step(client, token, bad).status_code == 423  # the third failure locks (limit 3)
    assert code_step(client, token, good).status_code == 423  # even the right code now
    assert password_step(client, "ada").status_code == 423
    assert "login_locked" in actions(engine)


@pytest.mark.db
def test_a_wrong_password_and_a_wrong_code_share_one_count(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    key, _, _ = set_up(client, "ada", clock)
    assert password_step(client, "ada", "nope").status_code == 401
    token = password_step(client, "ada").json()["mfa_token"]  # a right password does not clear it
    assert user_row(engine, "ada").failed_logins == 1
    bad = "000000" if now_code(key, clock) != "000000" else "111111"
    code_step(client, token, bad)
    assert code_step(client, token, bad).status_code == 423


@pytest.mark.db
def test_an_old_forged_or_out_of_date_2_step_token_means_start_again(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    key, _, h = set_up(client, "ada", clock)
    clock[0] += 30
    code = now_code(key, clock)
    for bad in ("not-a-token", h["Authorization"].removeprefix("Bearer ")):  # an access token too
        r = code_step(client, bad, code)
        assert r.status_code == 401 and r.json()["reason"] == "restart"
    uid = str(user_row(engine, "ada").id)
    late = jwt.encode({"sub": uid, "aud": MFA_AUDIENCE, "exp": datetime.now(UTC) - timedelta(seconds=1)},
                      SECRET, algorithm="HS256")  # fmt: skip
    assert code_step(client, late, code).json()["reason"] == "restart"
    forged = jwt.encode({"sub": uid, "aud": MFA_AUDIENCE, "exp": datetime.now(UTC) + timedelta(minutes=5)},
                        "another-secret-" + "z" * 32, algorithm="HS256")  # fmt: skip
    assert code_step(client, forged, code).json()["reason"] == "restart"
    # a password change after the password step ends that wait
    token = password_step(client, "ada").json()["mfa_token"]
    with engine.begin() as c:
        c.execute(text("UPDATE users SET password_hash = :h WHERE email = 'ada@example.test'"),
                  {"h": hash_password("a new password 123")})  # fmt: skip
    assert code_step(client, token, code).json()["reason"] == "restart"


@pytest.mark.db
def test_the_auditor_is_asked_too(client: TestClient, clock: list[float]) -> None:
    _, _, h = set_up(client, "aud", clock)
    assert client.get(f"{V1}/auth/me", headers=h).json()["role"] == "auditor"


@pytest.mark.db
def test_the_users_screen_shows_who_has_2_step(client: TestClient, clock: list[float]) -> None:
    _, _, ada = set_up(client, "ada", clock)
    rows = {u["email"]: u for u in client.get(f"{V1}/admin/users", headers=ada).json()}
    assert (
        rows["ada@example.test"]["two_step_since"] and rows["ada@example.test"]["two_step_required"]
    )
    assert rows["ari@example.test"]["two_step_since"] is None
    assert rows["ari@example.test"]["two_step_required"] is True
    assert rows["asha@example.test"]["two_step_required"] is False


@pytest.mark.db
def test_an_admin_resets_another_persons_2_step_with_a_reason_and_a_second_click(
    client: TestClient, engine: Engine, clock: list[float]
) -> None:
    _, _, ada = set_up(client, "ada", clock)
    set_up(client, "ari", clock)
    users = {u["email"]: u["id"] for u in client.get(f"{V1}/admin/users", headers=ada).json()}
    url = f"{V1}/admin/users/{users['ari@example.test']}/reset-two-step"
    reason = "Lost the phone on the train"
    assert client.post(url, headers=ada, json={"reason": reason}).status_code == 422  # one click
    assert (
        client.post(url, headers=ada, json={"second_click": True, "reason": "x"}).status_code == 422
    )
    own = f"{V1}/admin/users/{users['ada@example.test']}/reset-two-step"
    assert (
        client.post(own, headers=ada, json={"second_click": True, "reason": reason}).status_code
        == 409
    )
    aud = f"{V1}/admin/users/{users['aud@example.test']}/reset-two-step"
    assert (
        client.post(aud, headers=ada, json={"second_click": True, "reason": reason}).status_code
        == 403
    )
    asha = f"{V1}/admin/users/{users['asha@example.test']}/reset-two-step"
    assert (
        client.post(asha, headers=ada, json={"second_click": True, "reason": reason}).status_code
        == 409
    )
    r = client.post(url, headers=ada, json={"second_click": True, "reason": reason})
    assert r.status_code == 200 and r.json()["two_step_since"] is None
    row = user_row(engine, "ari")
    assert row.mfa_secret is None and row.mfa_enabled_at is None
    with engine.connect() as c:
        left = c.execute(text("SELECT count(*) FROM user_recovery_codes WHERE user_id = :u"),
                         {"u": row.id}).scalar_one()  # fmt: skip
        audit = c.execute(
            text("SELECT actor_id, after FROM audit_log WHERE action = 'two_step_reset'")
        ).one()
        mail = c.execute(
            text("SELECT subject, body FROM email_outbox WHERE kind = 'two_step_reset'")
        ).one()
    assert left == 0 and audit.after == {"reason": reason}
    assert "reset" in mail.subject and "QR code" in mail.body
    # ari scans a new QR code at the next sign-in
    assert password_step(client, "ari").json()["mfa"] == "setup"
    # an officer cannot reset anyone
    officer = password_step(client, "asha").json()["access_token"]
    assert client.post(url, headers={"Authorization": f"Bearer {officer}"},
                       json={"second_click": True, "reason": reason}).status_code == 403  # fmt: skip


@pytest.mark.db
def test_the_command_line_resets_an_admin_or_the_auditor(
    client: TestClient, engine: Engine, clock: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    set_up(client, "aud", clock)
    monkeypatch.setattr(users_cli, "create_engine", lambda *_a, **_k: engine)
    with pytest.raises(SystemExit):
        users_cli.main(["reset-2-step", "--email", "aud@example.test", "--reason", "short"])
    assert (
        users_cli.main(
            ["reset-2-step", "--email", "nobody@example.test", "--reason", "A new phone issued"]
        )
        == 1
    )
    assert (
        users_cli.main(
            ["reset-2-step", "--email", "AUD@example.test", "--reason", "A new phone issued"]
        )
        == 0
    )
    assert user_row(engine, "aud").mfa_enabled_at is None
    assert password_step(client, "aud").json()["mfa"] == "setup"
    with engine.connect() as c:
        audit = c.execute(
            text("SELECT actor_id, after FROM audit_log WHERE action = 'two_step_reset'")
        ).one()
    assert audit.actor_id is None and audit.after["by"] == "command line"
