from sqlalchemy import select

from app.models import AuditLog, User
from tests.conftest import DEFAULT_PASSWORD, login


def test_login_sets_httponly_cookie(client, make_user):
    make_user("alice@example.com")
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": DEFAULT_PASSWORD})
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com" and "password_hash" not in r.json()
    cookie = r.headers["set-cookie"]
    assert "mi_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()


def test_login_email_case_insensitive(client, make_user):
    make_user("alice@example.com")
    r = client.post("/api/auth/login", json={"email": "Alice@Example.COM", "password": DEFAULT_PASSWORD})
    assert r.status_code == 200


def test_login_wrong_password_401_generic(client, make_user):
    make_user("alice@example.com")
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong password!"})
    assert r.status_code == 401
    assert r.json()["error"] == {
        "code": "invalid_credentials",
        "message": "Incorrect email or password.",
        "details": None,
    }


def test_login_unknown_email_same_message(client):
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert r.status_code == 401 and r.json()["error"]["message"] == "Incorrect email or password."


def test_me_requires_cookie_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_me_rejects_garbage_token(client):
    client.cookies.set("mi_session", "not-a-jwt")
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_user_after_login(client, make_user):
    make_user("alice@example.com", account_label="Alice")
    login(client, "alice@example.com")
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "alice@example.com" and body["role"] == "user" and body["account_label"] == "Alice"
    assert body["last_login_at"] is not None


def test_inactive_user_rejected(client, db, make_user):
    u = make_user("alice@example.com")
    login(client, "alice@example.com")
    u.is_active = False
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": DEFAULT_PASSWORD})
    assert r.status_code == 401


def test_logout_clears_cookie(client, make_user):
    make_user("alice@example.com")
    login(client, "alice@example.com")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_writes_audit_row(client, db, make_user):
    u = make_user("alice@example.com")
    login(client, "alice@example.com")
    client.post("/api/auth/login", json={"email": "alice@example.com", "password": "nope nope nope"})
    actions = [(a.action, a.user_id) for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == [("auth.login", u.id), ("auth.login_failed", None)]


def test_bootstrap_admin_created_once(db):
    from app.auth.bootstrap import ensure_bootstrap_admin

    assert ensure_bootstrap_admin(db, "Boss@Example.com", "a-long-password") is True
    assert ensure_bootstrap_admin(db, "boss@example.com", "a-long-password") is False
    users = db.scalars(select(User)).all()
    assert len(users) == 1
    u = users[0]
    assert (u.email, u.role, u.access_scope, u.can_download) == ("boss@example.com", "admin", "all", True)


def test_bootstrap_skipped_when_users_exist(db, make_user):
    from app.auth.bootstrap import ensure_bootstrap_admin

    make_user("someone@example.com")
    assert ensure_bootstrap_admin(db, "boss@example.com", "a-long-password") is False


def test_login_attempts_are_rate_limited(client, make_user):
    from app.ratelimit import LOGIN_LIMIT_PER_MIN, login_limiter

    login_limiter.reset()
    make_user("alice@example.com")
    for _ in range(LOGIN_LIMIT_PER_MIN):
        assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong pass!"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "correct horse battery"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    login_limiter.reset()
