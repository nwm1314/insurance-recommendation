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

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_rate_limit_pytest.db"))
except OSError:
    pass

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.app.middleware.rate_limiter as rate_limiter_module
from backend.app.config import settings
from backend.app.dependencies import auth as auth_deps
from backend.app.dependencies.auth import get_client_ip
from backend.main import SecurityHeadersMiddleware
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


def test_xff_ignored_when_proxy_not_trusted(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 3)
    with TestClient(_make_app()) as client:
        for _ in range(3):
            assert client.get("/api/echo", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 200
        assert client.get("/api/echo", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 429
        # Spoofed XFF must not create a new bucket: the direct peer IP still holds.
        assert client.get("/api/echo", headers={"X-Forwarded-For": "5.6.7.8"}).status_code == 429


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


def test_user_limit_from_cookie_session(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 1000)
    monkeypatch.setattr(settings, "rate_limit_user_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_user_per_day", 1000)
    with TestClient(_make_app()) as client:
        client.cookies.set("access_token", _make_access_token(42))
        for _ in range(3):
            assert client.get("/api/echo").status_code == 200
        assert client.get("/api/echo").status_code == 429
        other = TestClient(_make_app())
        other.cookies.set("access_token", _make_access_token(99))
        with other:
            assert other.get("/api/echo").status_code == 200


def test_user_limit_prefers_authorization_over_cookie(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 1000)
    monkeypatch.setattr(settings, "rate_limit_user_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_user_per_day", 1000)
    headers = {"Authorization": f"Bearer {_make_access_token(7)}"}
    with TestClient(_make_app()) as client:
        client.cookies.set("access_token", _make_access_token(999))
        for _ in range(3):
            assert client.get("/api/echo", headers=headers).status_code == 200
        assert client.get("/api/echo", headers=headers).status_code == 429


def test_trusted_proxy_forwarded_for_used(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 3)
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1")
    monkeypatch.setattr(auth_deps, "_peer_is_trusted_proxy", lambda request: True)
    with TestClient(_make_app()) as client:
        for _ in range(3):
            assert client.get("/api/echo", headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}).status_code == 200
        assert client.get("/api/echo", headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}).status_code == 429
        # A different client behind the same proxy has its own bucket.
        assert client.get("/api/echo", headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}).status_code == 200


def test_admin_page_burst_with_default_limits():
    """The admin page fires 7 authenticated requests on load; defaults must not 429 it."""
    headers = {"Authorization": f"Bearer {_make_access_token(7)}"}
    with TestClient(_make_app()) as client:
        for _ in range(7):
            assert client.get("/api/echo", headers=headers).status_code == 200


class FakeRequest:
    def __init__(self, forwarded, host):
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        self.client = type("C", (), {"host": host})()


def test_get_client_ip_falls_back_to_client_host(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    assert _get_client_ip(FakeRequest("203.0.113.9, 10.0.0.1", "127.0.0.1")) == "127.0.0.1"
    assert _get_client_ip(FakeRequest(None, "127.0.0.1")) == "127.0.0.1"


def test_client_ip_ignores_spoofed_forwarded_for(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    monkeypatch.setattr(settings, "trusted_proxies", "")
    assert get_client_ip(FakeRequest("203.0.113.9", "127.0.0.1")) == "127.0.0.1"
    assert get_client_ip(FakeRequest(None, "127.0.0.1")) == "127.0.0.1"


def test_client_ip_uses_forwarded_for_only_from_trusted_peer(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1,10.0.0.0/8")
    trusted = FakeRequest("203.0.113.9, 10.0.0.7", "127.0.0.1")
    assert get_client_ip(trusted) == "203.0.113.9"
    untrusted_peer = FakeRequest("203.0.113.9, 10.0.0.7", "198.51.100.4")
    assert get_client_ip(untrusted_peer) == "198.51.100.4"


def test_client_ip_forwarded_for_all_trusted_falls_back_to_peer(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.0/8")
    assert get_client_ip(FakeRequest("10.0.0.7, 10.0.0.8", "10.0.0.8")) == "10.0.0.8"


def test_client_ip_malformed_forwarded_for_ignored(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")
    assert get_client_ip(FakeRequest("not-an-ip", "127.0.0.1")) == "127.0.0.1"


def _headers_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/echo")
    def echo():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_security_headers_present_by_default():
    with TestClient(_headers_app()) as client:
        resp = client.get("/api/echo")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert "strict-transport-security" not in resp.headers


def test_security_headers_toggle_and_hsts(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "hsts_enabled", True)
    with TestClient(_headers_app()) as client:
        resp = client.get("/api/echo")
        assert resp.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    monkeypatch.setattr(settings, "security_headers", False)
    with TestClient(_headers_app()) as client:
        resp = client.get("/api/echo")
        assert "x-content-type-options" not in resp.headers
        assert "x-frame-options" not in resp.headers


def test_auth_cookie_secure_flag_from_settings(monkeypatch):
    from starlette.responses import Response
    from backend.app.api.auth import _set_auth_cookies

    monkeypatch.setattr(settings, "cookie_secure", True)
    response = Response()
    _set_auth_cookies(response, "access-token-value", "refresh-token-value")
    set_cookie = response.headers["set-cookie"]
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    monkeypatch.setattr(settings, "cookie_secure", False)
    response = Response()
    _set_auth_cookies(response, "access-token-value", "refresh-token-value")
    assert "Secure" not in response.headers["set-cookie"]


def test_rate_limit_uses_single_atomic_increment_per_check(monkeypatch):
    """OPS-001：限流计数每次检查只发生一次原子 INCR（get+incr 两步竞态消除）。"""
    class CallCountingRedis(StubRedis):
        def __init__(self):
            super().__init__()
            self.incr_calls = 0
            self.get_calls = 0

        def get(self, key):
            self.get_calls += 1
            return super().get(key)

        def incr(self, key):
            self.incr_calls += 1
            return super().incr(key)

    class ScriptlessRedis(CallCountingRedis):
        """无 register_script 的客户端（回退路径：incr + 首次 setex）。"""

    app = _make_app()
    middleware = RateLimiterMiddleware(app)
    middleware.redis = ScriptlessRedis()
    middleware._script = None
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 3)

    # _check_ip_limit 是同步方法，直接串行调用 5 次
    results = [middleware._check_ip_limit("1.2.3.4") for _ in range(5)]
    assert results == [True, True, True, False, False], "超过 limit=3 后必须拒绝"
    assert middleware.redis.incr_calls == 5, "每次检查恰好一次 INCR（原子）"
    assert middleware.redis.get_calls == 0, "限流路径不得使用非原子的 get 预读"


def test_rate_limiter_fail_open_on_runtime_redis_error(monkeypatch, caplog):
    """OPS-001：Redis 运行期异常 → 请求放行（非 500），warning 仅一条。"""
    import logging

    class BrokenRedis:
        def ping(self):
            return True

        def register_script(self, lua):
            def run(keys, args):
                raise ConnectionError("redis down mid-flight")
            return run

    app = _make_app()
    middleware = RateLimiterMiddleware(app)
    middleware.redis = BrokenRedis()
    middleware._script = middleware.redis.register_script("")

    rate_limiter_module._REDIS_ERROR_FLAG["down"] = False
    with caplog.at_level(logging.WARNING, logger="backend.app.middleware.rate_limiter"):
        allowed = middleware._check_ip_limit("9.9.9.9")
    assert allowed is True, "Redis 故障必须 fail-open 放行"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "断路期间 warning 只应记录一次"
    assert rate_limiter_module._REDIS_ERROR_FLAG["down"] is True
    # 恢复：换回正常计数客户端后，flag 应被清除并恢复限流
    middleware.redis = StubRedis()
    middleware._script = None
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 120)
    allowed = middleware._check_ip_limit("9.9.9.9")
    assert allowed is True
    assert rate_limiter_module._REDIS_ERROR_FLAG["down"] is False, "恢复成功后应清除故障标记"
