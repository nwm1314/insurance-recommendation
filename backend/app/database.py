from pathlib import Path

from sqlalchemy import create_engine, event, inspect as sa_inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.app.config import settings, BASE_DIR

_IS_SQLITE = "sqlite" in settings.database_url


def ensure_sqlite_parent_dir(url: str) -> None:
    """Create the parent directory of a file-based SQLite database.

    SQLite refuses to create a missing directory, which breaks `alembic upgrade
    head` and `scripts/seed.py` on a fresh clone: `data/` is git-ignored, so the
    first command that opens the database fails with "unable to open database
    file" before the application has a chance to create the directory. This is
    a no-op for in-memory URLs and for non-SQLite backends.
    """
    if not url.startswith("sqlite"):
        return
    database = make_url(url).database
    if not database or database == ":memory:":
        return
    parent = Path(database).expanduser().parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


ensure_sqlite_parent_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    # OPS-005：SQLite 增加 busy_timeout 连接参数，降低并发写锁冲突
    connect_args={"check_same_thread": False, "timeout": 30} if _IS_SQLITE else {},
    echo=False,
)

if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        # OPS-005：WAL 允许读写并发，busy_timeout 兜底写锁等待（毫秒）
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

ALEMBIC_INI = BASE_DIR / "alembic.ini"


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _import_models():
    from backend.app.models.product import Product  # noqa
    from backend.app.models.rule import Rule  # noqa
    from backend.app.models.benefit import Benefit  # noqa
    from backend.app.models.page_log import PageLog  # noqa
    from backend.app.models.auth import (  # noqa
        AuditLog,
        Permission,
        RecommendationRecord,
        RefreshToken,
        Role,
        RolePermission,
        SavedProfile,
        User,
        UserRole,
    )
    from backend.app.models.data_ingestion import (  # noqa
        CrawlJob,
        CrawlRun,
        ExtractionRun,
        ProductDraft,
        ProductFieldEvidence,
        ProductReviewTask,
        ProductVersion,
        RawDocument,
        SourcePage,
        SourcePlatform,
    )


def _alembic_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()


def _stamp_alembic_head(bind=None) -> None:
    bind = bind or engine
    head = _alembic_head()
    with bind.begin() as conn:
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
            {"version": head},
        )


def verify_schema_integrity(bind=None) -> None:
    _import_models()
    bind = bind or engine
    inspector = sa_inspect(bind)
    tables = set(inspector.get_table_names())
    if not tables:
        return
    if "alembic_version" not in tables:
        raise RuntimeError(
            "Database contains tables but has no Alembic version record. "
            "Run 'alembic upgrade head' (see docs/docker-deployment.md) "
            "before starting the application."
        )
    with bind.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    head = _alembic_head()
    if version != head:
        raise RuntimeError(
            f"Database schema is at migration {version!r} but the current Alembic "
            f"head is {head!r}. Run 'alembic upgrade head' (see docs/docker-deployment.md) "
            "before starting the application."
        )
    model_tables = set(Base.metadata.tables.keys())
    for name in sorted(model_tables):
        if name not in tables:
            raise RuntimeError(
                f"Table '{name}' is missing from the database. "
                "Run 'alembic upgrade head' before starting the application."
            )
        columns = {c["name"] for c in inspector.get_columns(name)}
        expected = {c.name for c in Base.metadata.tables[name].columns}
        missing = sorted(expected - columns)
        if missing:
            raise RuntimeError(
                f"Table '{name}' is missing columns {missing}. "
                "Run 'alembic upgrade head' before starting the application."
            )


def init_db():
    _import_models()
    if not sa_inspect(engine).get_table_names():
        Base.metadata.create_all(bind=engine)
        _stamp_alembic_head()
    else:
        verify_schema_integrity()
