"""OPS-002 回归：登录防爆破与推荐记录落库加密。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_ops002_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_ops002_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.models.auth import RecommendationRecord, User

init_db()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


class StubRedis:
    """带 delete/expire 的最小 Redis stub（防爆破计数）。"""

    def __init__(self):
        self.data: dict[str, str] = {}

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = str(value)

    def set(self, key, value):
        self.data[key] = str(value)

    def incr(self, key):
        current = int(self.data.get(key, "0"))
        self.data[key] = str(current + 1)
        return current + 1

    def expire(self, key, ttl):
        pass

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)


def _register(client, email, password="Str0ngPass!x"):
    return client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": "爆破测试",
    })


def test_login_bruteforce_lockout_and_reset(client, monkeypatch):
    """OPS-002：5 次失败后第 6 次 429；成功登录后计数清零。"""
    import backend.app.api.auth as auth_api

    stub = StubRedis()
    monkeypatch.setattr(auth_api, "_get_redis_client", lambda: stub)

    email = "bruteforce@example.com"
    created = _register(client, email)
    assert created.status_code in (200, 201), created.text

    # 5 次错误密码 → 全部 401；锁定期间即使密码正确也 429（防爆破标准语义：
    # 攻击者不能靠已泄露的正确密码绕过锁定）
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert resp.status_code == 401
    ok = client.post("/api/auth/login", json={"email": email, "password": "Str0ngPass!x"})
    assert ok.status_code == 429, ok.text
    assert "过于频繁" in ok.json()["detail"]

    # 模拟锁定窗口 TTL 过期（计数消失）→ 正确登录成功 → 清零
    stub.data = {k: v for k, v in stub.data.items() if not k.startswith("login_fail")}
    success = client.post("/api/auth/login", json={"email": email, "password": "Str0ngPass!x"})
    assert success.status_code == 200, success.text
    assert all(not k.startswith("login_fail") for k in stub.data), "成功登录应清零失败计数"
    again = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert again.status_code == 401, "清零后正常计数，而非直接 429"


def test_login_bruteforce_fails_open_without_redis(client, monkeypatch):
    """OPS-002：Redis 不可用 → 防爆破跳过（fail-open），登录不受影响。"""
    import backend.app.api.auth as auth_api

    monkeypatch.setattr(auth_api, "_get_redis_client", lambda: None)
    email = "failopen@example.com"
    created = _register(client, email)
    assert created.status_code in (200, 201), created.text

    for _ in range(7):
        resp = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert resp.status_code == 401, "无 Redis 时不得 429（fail-open）"
    ok = client.post("/api/auth/login", json={"email": email, "password": "Str0ngPass!x"})
    assert ok.status_code == 200


def test_record_encryption_roundtrip_and_plaintext_hidden(client, monkeypatch):
    """OPS-002：设置加密密钥后，绕过 ORM 直接 SQL 查询 profile 列看不到
    健康明文；API 读回内容与写入一致。"""
    from sqlalchemy import text as sql_text

    monkeypatch.setattr(settings, "record_encryption_key", "test-secret-key-ops002")

    payload = {
        "age": 30, "gender": "male", "annual_income": 100000, "job_class": 1,
        "life_stage": "single", "family_burden": "none", "health_status": "standard",
        "health_issues": ["甲状腺结节"], "existing_coverage": [],
        "budget_ratio": 0.08, "enable_llm_engine": False,
    }
    resp = client.post("/api/recommend", json=payload)
    assert resp.status_code == 200, resp.text

    db = SessionLocal()
    try:
        row = db.execute(
            sql_text("SELECT profile FROM recommendation_records ORDER BY id DESC LIMIT 1")
        ).fetchone()
        raw_profile = row[0]
        raw_text = raw_profile if isinstance(raw_profile, str) else str(raw_profile)
        assert "甲状腺结节" not in raw_text, "落库内容不得含健康明文"

        # API 读回内容与写入一致（读路径自动解密）
        records = client.get("/api/my/recommendations")
        if records.status_code == 200:
            body = records.json()
            items = body.get("records") if isinstance(body, dict) else body
            if items:
                assert items[0]["profile"].get("health_issues") == ["甲状腺结节"], "API 读回应还原明文"
    finally:
        db.close()

    monkeypatch.setattr(settings, "record_encryption_key", "")


def test_encrypted_json_type_tolerates_legacy_plaintext(monkeypatch):
    """历史明文行（密钥为空时期写入）在开启加密后仍可正常读取。"""
    db = SessionLocal()
    try:
        user = db.query(User).first()
        assert user is not None, "需要至少一个用户（seed 注册）"
        record = RecommendationRecord(user_id=user.id, profile={"legacy": True}, result={"legacy": "result"})
        db.add(record)
        db.commit()
        record_id = record.id
    finally:
        db.close()

    monkeypatch.setattr(settings, "record_encryption_key", "later-enabled-key")

    db = SessionLocal()
    try:
        record = db.query(RecommendationRecord).filter(RecommendationRecord.id == record_id).first()
        assert record.profile == {"legacy": True}, "历史明文 dict 应原样读出"
    finally:
        db.close()
