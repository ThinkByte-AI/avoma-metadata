from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import login

NEW_USER = {
    "email": "Bob@Example.com",
    "name": "Bob",
    "password": "bob-password-123",
    "role": "user",
    "access_scope": "own",
    "account_label": "Bob",
    "can_download": False,
}


def test_standard_user_cannot_list_users_403(client, make_user):
    make_user("alice@example.com")
    login(client, "alice@example.com")
    r = client.get("/api/users")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


def test_admin_lists_users(admin_client):
    r = admin_client.get("/api/users")
    assert r.status_code == 200 and [u["email"] for u in r.json()] == ["admin@example.com"]


def test_admin_creates_user_and_email_lowercased(admin_client, client, db):
    r = admin_client.post("/api/users", json=NEW_USER)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "bob@example.com" and r.json()["account_label"] == "Bob"
    login(client, "bob@example.com", "bob-password-123")


def test_short_password_422(admin_client):
    r = admin_client.post("/api/users", json={**NEW_USER, "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_invalid_role_422(admin_client):
    r = admin_client.post("/api/users", json={**NEW_USER, "role": "superuser"})
    assert r.status_code == 422


def test_duplicate_email_409(admin_client):
    assert admin_client.post("/api/users", json=NEW_USER).status_code == 201
    r = admin_client.post("/api/users", json={**NEW_USER, "email": "bob@example.com"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_admin_updates_user(admin_client, client):
    uid = admin_client.post("/api/users", json=NEW_USER).json()["id"]
    r = admin_client.patch(f"/api/users/{uid}", json={"access_scope": "all", "can_download": True})
    assert r.status_code == 200 and r.json()["access_scope"] == "all" and r.json()["can_download"] is True
    r = admin_client.patch(f"/api/users/{uid}", json={"password": "new-password-456"})
    assert r.status_code == 200
    login(client, "bob@example.com", "new-password-456")
    admin_client.patch(f"/api/users/{uid}", json={"is_active": False})
    assert client.get("/api/auth/me").status_code == 401


def test_update_missing_user_404(admin_client):
    assert admin_client.patch("/api/users/9999", json={"name": "x"}).status_code == 404


def test_user_changes_are_audited(admin_client, db):
    uid = admin_client.post("/api/users", json=NEW_USER).json()["id"]
    admin_client.patch(f"/api/users/{uid}", json={"name": "Bobby"})
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions[-2:] == ["user.create", "user.update"]
