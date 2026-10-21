"""REC-006：推荐记录保留策略的回归测试。

覆盖三件事：
1. `RECORD_RETENTION_DAYS=0`（默认）不删除任何数据——与引入配置前行为一致；
2. 窗口内的记录保留、窗口外的记录删除，且只删 recommendation_records；
3. dry-run 只统计不落删，且保留天数未配置时不注册调度任务。
"""

import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.gettempdir(), "insurance_retention_pytest.db").replace(os.sep, "/"),
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_retention_pytest.db"))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from backend.main import app
from backend.app.config import settings
from backend.app.crawler import scheduler as scheduler_module
from backend.app.database import SessionLocal
from backend.app.models.auth import (
    RecommendationRecord,
    RefreshToken,
    SavedProfile,
    User,
    UserRole,
)
from backend.app.services.retention import purge_expired_recommendation_records
from backend.app.time import utc_now


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    db = SessionLocal()
    try:
        db.query(RecommendationRecord).delete()
        db.query(SavedProfile).delete()
        db.query(RefreshToken).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


def _make_user(db, email: str) -> User:
    user = User(email=email, password_hash="x", status="active", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_record(db, user: User, age_days: int) -> RecommendationRecord:
    record = RecommendationRecord(
        user_id=user.id,
        profile={"age": 30},
        result={"packages": []},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    db.execute(
        update(RecommendationRecord)
        .where(RecommendationRecord.id == record.id)
        .values(created_at=utc_now() - timedelta(days=age_days))
    )
    db.commit()
    return record


def _record_ids(db) -> set[int]:
    return {row.id for row in db.query(RecommendationRecord.id).all()}


def test_zero_days_keeps_everything(client):
    db = SessionLocal()
    try:
        user = _make_user(db, "keep@example.com")
        _make_record(db, user, age_days=4000)

        result = purge_expired_recommendation_records(db, 0)

        assert result.enabled is False
        assert result.deleted == 0
        assert len(_record_ids(db)) == 1
    finally:
        db.close()


def test_dry_run_counts_without_deleting(client):
    db = SessionLocal()
    try:
        user = _make_user(db, "dryrun@example.com")
        old = _make_record(db, user, age_days=100)

        result = purge_expired_recommendation_records(db, 30, dry_run=True)

        assert result.enabled is True
        assert result.matched == 1
        assert result.deleted == 0
        assert old.id in _record_ids(db)
    finally:
        db.close()


def test_deletes_only_records_older_than_window(client):
    db = SessionLocal()
    try:
        user = _make_user(db, "window@example.com")
        expired = _make_record(db, user, age_days=100)
        fresh = _make_record(db, user, age_days=10)
        # 窗口边缘内侧：29 天 < 30 天，必须保留。用 29 而非 30 是为了避开
        # 记录创建与 cutoff 计算之间的微秒级时钟差。
        near_boundary = _make_record(db, user, age_days=29)
        # 删除后 ORM 实例会失效，先取出 id 再执行清理。
        expired_id, fresh_id, near_boundary_id = expired.id, fresh.id, near_boundary.id

        result = purge_expired_recommendation_records(db, 30)

        assert result.matched == 1
        assert result.deleted == 1
        remaining = _record_ids(db)
        assert expired_id not in remaining
        assert fresh_id in remaining
        assert near_boundary_id in remaining
    finally:
        db.close()


def test_retention_job_is_not_registered_when_disabled():
    original = settings.record_retention_days
    settings.record_retention_days = 0
    try:
        scheduler_module.scheduler.remove_all_jobs()
        scheduler_module.register_retention_job()
        job_ids = {job.id for job in scheduler_module.scheduler.get_jobs()}
        assert scheduler_module.RETENTION_JOB_ID not in job_ids
    finally:
        scheduler_module.scheduler.remove_all_jobs()
        settings.record_retention_days = original


def test_retention_job_registers_when_configured():
    original = settings.record_retention_days
    settings.record_retention_days = 90
    try:
        scheduler_module.scheduler.remove_all_jobs()
        scheduler_module.register_retention_job()
        job_ids = {job.id for job in scheduler_module.scheduler.get_jobs()}
        assert scheduler_module.RETENTION_JOB_ID in job_ids
    finally:
        scheduler_module.scheduler.remove_all_jobs()
        settings.record_retention_days = original


def test_saved_profiles_are_not_retention_targets(client):
    """保留策略只覆盖推荐记录；用户主动保存的画像不由该任务删除。"""
    db = SessionLocal()
    try:
        user = _make_user(db, "profiles@example.com")
        profile = SavedProfile(user_id=user.id, name="mine", profile={"age": 30})
        db.add(profile)
        db.commit()
        db.refresh(profile)
        db.execute(
            update(SavedProfile)
            .where(SavedProfile.id == profile.id)
            .values(created_at=utc_now() - timedelta(days=4000))
        )
        db.commit()

        result = purge_expired_recommendation_records(db, 30)

        assert result.deleted == 0
        assert db.query(SavedProfile).filter(SavedProfile.id == profile.id).first() is not None
    finally:
        db.close()
