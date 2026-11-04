"""Sessions: a 15-minute access token renewed from an HttpOnly refresh cookie, an idle timeout and
a 12-hour maximum enforced on the server, rotation with theft detection, and logout that really
ends the session. Same throwaway database and fixtures as the API tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.auth import COOKIE
from tests import test_api
from tests.test_api import PASSWORD

pytestmark = pytest.mark.db
client = test_api.client  # the same app, database and users as the API tests
engine = test_api.engine


def sign_in(client: TestClient, who: str = "asha") -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login", json={"email": f"{who}@example.test", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def present(client: TestClient, value: str | None) -> None:
    """Make the browser send exactly this refresh cookie (replacing the one it holds)."""
    client.cookies.clear()
    client.cookies.set(COOKIE, value or "")


def age(engine: Engine, **columns: str) -> None:
    """Move the (only) session's clocks back, e.g. last_active='31 minutes'."""
    sets = ", ".join(f"{c} = now() - interval '{v}'" for c, v in columns.items())
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE user_sessions SET {sets}"))  # noqa: S608 - test-only literals


def actions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT action FROM audit_log ORDER BY id"))]


def test_login_sets_an_http_only_cookie_and_reports_the_limits(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "asha@example.test", "password": PASSWORD})
    header = r.headers["set-cookie"].lower()
    assert COOKIE in header and "httponly" in header and "samesite=strict" in header
    assert "max-age" not in header and "path=/api/v1/auth" in header
    session = r.json()["session"]
    assert session["access_token_seconds"] == 15 * 60
    assert session["idle_timeout_seconds"] == 30 * 60
    assert session["idle_warning_seconds"] == 2 * 60
    assert "refresh" not in r.text  # the secret never reaches page JavaScript


def test_refresh_gives_a_new_token_and_rotates_the_cookie(client: TestClient) -> None:
    sign_in(client)
    first = client.cookies.get(COOKIE)
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["email"] == "asha@example.test"
    assert client.cookies.get(COOKIE) != first
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/cases", headers=h).status_code == 200


def test_no_cookie_or_a_guessed_one_is_refused(client: TestClient) -> None:
    assert client.post("/api/v1/auth/refresh").status_code == 401
    sign_in(client)
    sid = client.cookies.get(COOKIE).split(".")[0]  # type: ignore[union-attr]
    present(client, f"{sid}.not-the-secret")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_idle_session_is_ended_by_the_server_for_tokens_and_refresh(
    client: TestClient, engine: Engine
) -> None:
    h = sign_in(client)
    age(engine, last_active="31 minutes")
    assert client.get("/api/v1/cases", headers=h).status_code == 401
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["reason"] == "idle"
    assert "session_idle_end" in actions(engine)
    assert client.post("/api/v1/auth/refresh").status_code == 401  # and stays ended


def test_ping_keeps_an_active_session_alive_but_refresh_alone_does_not(
    client: TestClient, engine: Engine
) -> None:
    h = sign_in(client)
    age(engine, last_active="29 minutes")
    assert client.post("/api/v1/auth/ping", headers=h).status_code == 200
    age(engine, last_active="29 minutes")
    assert client.post("/api/v1/auth/refresh").status_code == 200  # refresh did not touch it
    age(engine, last_active="29 minutes")
    r = client.post("/api/v1/auth/refresh")
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with engine.connect() as conn:
        idle = conn.execute(
            text("SELECT extract(epoch FROM now() - last_active) FROM user_sessions")
        ).scalar_one()
    assert idle > 28 * 60 and client.get("/api/v1/cases", headers=h2).status_code == 200


def test_twelve_hour_limit_holds_however_active_the_user_is(
    client: TestClient, engine: Engine
) -> None:
    h = sign_in(client)
    age(engine, started_at="12 hours 1 minute")
    assert client.post("/api/v1/auth/ping", headers=h).status_code == 401
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["reason"] == "max"
    assert "session_max_end" in actions(engine)


def test_reusing_an_old_refresh_token_closes_the_session(
    client: TestClient, engine: Engine
) -> None:
    sign_in(client)
    old = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 200  # rotated
    age(engine, rotated_at="1 minute")  # outside the second-tab grace window
    present(client, old)  # the thief replays the old one
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["reason"] == "reuse"
    assert "token_reuse" in actions(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT revoked_reason FROM user_sessions")).scalar() == "reuse"


def test_a_second_tab_a_moment_later_gets_a_token_without_closing_the_session(
    client: TestClient,
) -> None:
    sign_in(client)
    old = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    current = client.cookies.get(COOKIE)
    present(client, old)
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and "set-cookie" not in r.headers
    present(client, current)
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_logout_ends_the_session_and_the_access_token_stops_working(
    client: TestClient, engine: Engine
) -> None:
    h = sign_in(client)
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/cases", headers=h).status_code == 401  # even before it expires
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert "logout" in actions(engine)


def test_deactivating_a_user_ends_refresh_too(client: TestClient, engine: Engine) -> None:
    sign_in(client)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET active = false WHERE email = 'asha@example.test'"))
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["reason"] == "inactive"


def test_each_sign_in_is_its_own_session(client: TestClient, engine: Engine) -> None:
    first = sign_in(client)
    other = TestClient(client.app)
    second = sign_in(other)
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/cases", headers=first).status_code == 401
    assert other.get("/api/v1/cases", headers=second).status_code == 200
