from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
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
    Base.metadata.create_all(bind=engine)
