import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_admin_bootstrap_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_admin_bootstrap_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models.auth import AuditLog, RefreshToken, SavedProfile, User, UserRole
from backend.app.services.auth_service import create_user, ensure_auth_defaults


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    db = SessionLocal()
    try:
        db.query(AuditLog).delete()
        db.query(RefreshToken).delete()
        db.query(SavedProfile).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


def _bootstrap_admin(monkeypatch, email="bootstrap-admin@example.com", password="Password12345"):
    monkeypatch.setattr(settings, "first_admin_email", email)
    monkeypatch.setattr(settings, "first_admin_password", password)
    db = SessionLocal()
    try:
        ensure_auth_defaults(db)
    finally:
        db.close()


def _register(client, email, password="Password12345"):
    response = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": email})
    assert response.status_code == 200, response.text
    return response.json()


def _login_token(client, email, password="Password12345"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client.cookies.get("access_token")


def test_empty_db_register_gets_user_role_only(client):
    registered = _register(client, "empty-db-user@example.com")
    assert registered["roles"] == ["user"]
    assert "admin:grant" not in registered["permissions"]
    assert "product:write" not in registered["permissions"]
    assert "crawl:trigger" not in registered["permissions"]


def test_first_admin_bootstrap_via_env_is_audited(monkeypatch):
    _bootstrap_admin(monkeypatch)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "bootstrap-admin@example.com").first()
        assert admin is not None
        assert [ur.role.name for ur in admin.roles] == ["admin"]
        audits = db.query(AuditLog).filter(AuditLog.action == "auth.first_admin.bootstrap").all()
        assert len(audits) == 1
        assert audits[0].user_id == admin.id
        assert audits[0].detail == {"source": "env"}
        assert "Password12345" not in str(audits[0].detail)
        ensure_auth_defaults(db)
        db.expire_all()
        assert db.query(User).filter(User.email == "bootstrap-admin@example.com").count() == 1
        assert db.query(AuditLog).filter(AuditLog.action == "auth.first_admin.bootstrap").count() == 1
    finally:
        db.close()


def test_register_after_admin_exists_gets_user_role(client, monkeypatch):
    _bootstrap_admin(monkeypatch)
    registered = _register(client, "after-admin-user@example.com")
    assert registered["roles"] == ["user"]
    assert "admin:grant" not in registered["permissions"]


def _register_in_thread(email, results, index):
    db = SessionLocal()
    try:
        try:
            user = create_user(db, email, "Password12345")
            results[index] = ("ok", user.id)
        except ValueError as exc:
            results[index] = ("conflict", str(exc))
    finally:
        db.close()


def test_concurrent_registration_no_privilege_escalation():
    results = [None, None]
    threads = [
        threading.Thread(target=_register_in_thread, args=("concurrent-a@example.com", results, 0)),
        threading.Thread(target=_register_in_thread, args=("concurrent-b@example.com", results, 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert results[0][0] == "ok"
    assert results[1][0] == "ok"
    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.email.in_(["concurrent-a@example.com", "concurrent-b@example.com"])
        ).all()
        assert len(users) == 2
        for user in users:
            assert [ur.role.name for ur in user.roles] == ["user"]
    finally:
        db.close()


def test_concurrent_same_email_single_success():
    results = [None, None]
    threads = [
        threading.Thread(target=_register_in_thread, args=("same-email@example.com", results, 0)),
        threading.Thread(target=_register_in_thread, args=("same-email@example.com", results, 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    outcomes = sorted(r[0] for r in results)
    assert outcomes == ["conflict", "ok"]
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "same-email@example.com").count() == 1
    finally:
        db.close()


def test_grant_admin_role_requires_admin_permission(client, monkeypatch):
    _bootstrap_admin(monkeypatch)
    target = _register(client, "target-user@example.com")
    admin_token = _login_token(client, "bootstrap-admin@example.com")
    user_token = _login_token(client, "target-user@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}
    client.cookies.clear()

    assert client.post(f"/api/admin/users/{target['id']}/roles", json={"roles": ["admin"]}).status_code == 401
    resp = client.post(f"/api/admin/users/{target['id']}/roles", headers=user_headers, json={"roles": ["admin"]})
    assert resp.status_code == 403

    resp = client.post(f"/api/admin/users/{target['id']}/roles", headers=admin_headers, json={"roles": ["admin"]})
    assert resp.status_code == 200, resp.text
    assert "admin" in resp.json()["roles"]
    assert "admin:grant" in resp.json()["permissions"]

    db = SessionLocal()
    try:
        audit = db.query(AuditLog).filter(AuditLog.action == "admin.roles.update").first()
        assert audit is not None
        assert audit.detail == {"from": ["user"], "to": ["admin"]}
        admin = db.query(User).filter(User.email == "bootstrap-admin@example.com").first()
        admin_id = admin.id
    finally:
        db.close()

    resp = client.post("/api/admin/users/999999/roles", headers=admin_headers, json={"roles": ["admin"]})
    assert resp.status_code == 404

    resp = client.post(f"/api/admin/users/{target['id']}/roles", headers=admin_headers, json={"roles": ["superuser"]})
    assert resp.status_code == 400

    resp = client.post(f"/api/admin/users/{admin_id}/roles", headers=admin_headers, json={"roles": []})
    assert resp.status_code == 400

    resp = client.post(f"/api/admin/users/{admin_id}/roles", headers=admin_headers, json={"roles": ["user"]})
    assert resp.status_code == 400

    resp = client.post(f"/api/admin/users/{target['id']}/roles", headers=admin_headers, json={"roles": ["user"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["user"]
