"""Shared idempotent schema helpers used by Alembic migrations.

The pre-existing SQLite database was created with ``create_all()`` and has no
Alembic history, and the first two migrations never created the catalog
tables (products/rules/benefits/page_logs) yet reference ``products.id``.
Every helper below is safe to run against an empty database, a partially
migrated one, or a fully ``create_all()``-created legacy database.
"""
import sqlalchemy as sa
from alembic import op

from backend.app.database import Base
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

ALL_TABLE_NAMES = sorted(Base.metadata.tables.keys())

CREATED_TABLES: set[str] = set()


def ensure_tables(bind, table_names):
    inspector = sa.inspect(bind)
    for name in table_names:
        if inspector.has_table(name):
            continue
        table = Base.metadata.tables[name]
        table.create(bind)
        CREATED_TABLES.add(name)
        for index in table.indexes:
            index.create(bind, checkfirst=True)


def align_columns(bind, table_names, added=None):
    inspector = sa.inspect(bind)
    for name in table_names:
        if not inspector.has_table(name):
            continue
        existing = {c["name"] for c in inspector.get_columns(name)}
        for column in Base.metadata.tables[name].columns:
            if column.name in existing:
                continue
            if not column.nullable and column.server_default is None:
                raise RuntimeError(
                    f"Cannot add non-nullable column {name}.{column.name} without a "
                    "server default; add a dedicated migration instead"
                )
            op.add_column(
                name,
                sa.Column(
                    column.name,
                    column.type,
                    nullable=column.nullable,
                    server_default=column.server_default,
                ),
            )
            if added is not None:
                added.append((name, column.name))


def align_indexes(bind, table_names):
    inspector = sa.inspect(bind)
    for name in table_names:
        if not inspector.has_table(name):
            continue
        existing = {i["name"] for i in inspector.get_indexes(name)}
        for index in Base.metadata.tables[name].indexes:
            if index.name in existing:
                continue
            op.create_index(
                index.name,
                name,
                [c.name for c in index.columns],
                unique=bool(index.unique),
            )


def align_schema(bind, table_names):
    ensure_tables(bind, table_names)
    align_columns(bind, table_names)
    align_indexes(bind, table_names)


def drop_table_if_created(bind, table_name):
    if table_name not in CREATED_TABLES:
        return
    if not sa.inspect(bind).has_table(table_name):
        return
    op.drop_table(table_name)
