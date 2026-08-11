import importlib
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.app.config import BASE_DIR, settings
from backend.app.database import Base, verify_schema_integrity
from backend.app.models.product import Product
import backend.app.migrations as migrations

HEAD = "20260811_0001"
MODEL_TABLE_COUNT = 23


def _config(url: str) -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _upgrade(url: str, target: str = "head") -> None:
    with patch.object(settings, "database_url", url):
        command.upgrade(_config(url), target)


def _downgrade(url: str, target: str) -> None:
    with patch.object(settings, "database_url", url):
        command.downgrade(_config(url), target)


def _connect(url: str):
    return sa.create_engine(url)


def _table_names(url: str):
    engine = _connect(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_empty_db_upgrade_creates_full_schema(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    _upgrade(url)
    tables = _table_names(url)
    assert "alembic_version" in tables
    assert len(tables) - 1 == MODEL_TABLE_COUNT
    engine = _connect(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == HEAD
        columns = {c["name"] for c in sa.inspect(engine).get_columns("products")}
        assert "deductible" in columns
        verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_legacy_create_all_db_upgrade_preserves_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = _connect(url)
    Base.metadata.create_all(bind=engine)
    with sa.orm.Session(engine) as session:
        session.add(Product(name="旧产品", company="测试公司", type="医疗险", status=1, premium_min=100))
        session.commit()
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE products DROP COLUMN deductible"))
    engine.dispose()

    _upgrade(url)
    engine = _connect(url)
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            count = conn.execute(sa.text("SELECT COUNT(*) FROM products")).scalar()
        assert version == HEAD
        assert count == 1
        columns = {c["name"] for c in sa.inspect(engine).get_columns("products")}
        assert "deductible" in columns
        verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_downgrade_to_0002_then_upgrade_again(tmp_path):
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    _upgrade(url)
    assert _table_names(url) == set(Base.metadata.tables) | {"alembic_version"}

    _downgrade(url, "20260706_0002")
    tables = _table_names(url)
    assert "products" in tables
    assert "source_platforms" in tables
    engine = _connect(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "20260706_0002"
    finally:
        engine.dispose()

    _downgrade(url, "20260706_0001")
    tables = _table_names(url)
    assert "products" not in tables
    assert "source_platforms" not in tables
    assert "users" in tables
    engine = _connect(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "20260706_0001"
    finally:
        engine.dispose()

    _upgrade(url)
    assert _table_names(url) == set(Base.metadata.tables) | {"alembic_version"}
    engine = _connect(url)
    try:
        verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_gate_rejects_unmigrated_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'unmigrated.db'}"
    engine = _connect(url)
    Base.metadata.create_all(bind=engine)
    try:
        with pytest.raises(RuntimeError, match="no Alembic version"):
            verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_gate_rejects_stale_revision(tmp_path):
    url = f"sqlite:///{tmp_path / 'stale.db'}"
    _upgrade(url)
    engine = _connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE alembic_version SET version_num = '20260706_0002'"))
        with pytest.raises(RuntimeError, match="head"):
            verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_gate_rejects_missing_columns_at_head(tmp_path):
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    _upgrade(url)
    engine = _connect(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("ALTER TABLE products DROP COLUMN deductible"))
        with pytest.raises(RuntimeError, match="missing columns"):
            verify_schema_integrity(bind=engine)
    finally:
        engine.dispose()


def test_migration_module_imports_all_models():
    import backend.app.models.auth  # noqa
    import backend.app.models.benefit  # noqa
    import backend.app.models.data_ingestion  # noqa
    import backend.app.models.page_log  # noqa
    import backend.app.models.product  # noqa
    import backend.app.models.rule  # noqa
    assert len(migrations.ALL_TABLE_NAMES) == MODEL_TABLE_COUNT
