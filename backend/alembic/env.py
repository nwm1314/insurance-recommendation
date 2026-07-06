from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from backend.app.config import settings
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

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
