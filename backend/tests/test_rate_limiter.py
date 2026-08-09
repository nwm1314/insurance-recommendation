import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_rate_limit_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.app.middleware.rate_limiter as rate_limiter_module
from backend.app.config import settings
from backend.app.middleware.rate_limiter import RateLimiterMiddleware, _get_client_ip


class StubRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    def ping(self):
        return True

    def get(self, key: str):
        return self.data.get(key)

    def setex(self, key: str, ttl: int, value):
        self.data[key] = str(value)

    def incr(self, key: str) -> int:
        current = int(self.data.get(key, "0"))
        self.data[key] = str(current + 1)
        return current + 1


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/echo")
    def echo():
        return {"ok": True}

    app.add_middleware(RateLimiterMiddleware)
    return app


def _make_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest.fixture(autouse=True)
def stub_redis(monkeypatch):
    monkeypatch.setattr(rate_limiter_module.redis, "from_url", lambda *a, **k: StubRedis())
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 120)
    monkeypatch.setattr(settings, "rate_limit_user_per_minute", 30)
    monkeypatch.setattr(settings, "rate_limit_user_per_day", 300)


def test_ip_limit_uses_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 3)
    with TestClient(_make_app()) as client:
        for _ in range(3):
            assert client.get("/api/echo", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 200
        assert client.get("/api/echo", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 429
        assert client.get("/api/echo", headers={"X-Forwarded-For": "5.6.7.8"}).status_code == 200


def test_user_limit_per_minute(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 1000)
    monkeypatch.setattr(settings, "rate_limit_user_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_user_per_day", 1000)
    headers = {"Authorization": f"Bearer {_make_access_token(42)}"}
    with TestClient(_make_app()) as client:
        for _ in range(3):
            assert client.get("/api/echo", headers=headers).status_code == 200
        assert client.get("/api/echo", headers=headers).status_code == 429
        other = {"Authorization": f"Bearer {_make_access_token(99)}"}
        assert client.get("/api/echo", headers=other).status_code == 200


def test_admin_page_burst_with_default_limits():
    """The admin page fires 7 authenticated requests on load; defaults must not 429 it."""
    headers = {"Authorization": f"Bearer {_make_access_token(7)}"}
    with TestClient(_make_app()) as client:
        for _ in range(7):
            assert client.get("/api/echo", headers=headers).status_code == 200


def test_get_client_ip_falls_back_to_client_host():
    class FakeRequest:
        def __init__(self, forwarded, host):
            self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
            self.client = type("C", (), {"host": host})()

    assert _get_client_ip(FakeRequest("203.0.113.9, 10.0.0.1", "127.0.0.1")) == "203.0.113.9"
    assert _get_client_ip(FakeRequest(None, "127.0.0.1")) == "127.0.0.1"
