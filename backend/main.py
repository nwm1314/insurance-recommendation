import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import safe_llm_base_url, settings
from backend.app.database import init_db
from backend.app.api.products import router as products_router
from backend.app.api.recommend import router as recommend_router
from backend.app.api.admin import router as admin_router
from backend.app.api.auth import router as auth_router
from backend.app.api.ingestion import router as ingestion_router
from backend.app.middleware.rate_limiter import RateLimiterMiddleware
from backend.app.crawler.scheduler import init_scheduler
from backend.app.database import SessionLocal
from backend.app.services.auth_service import ensure_auth_defaults
from backend.app.data_ingestion.pipeline import ensure_seed_products_if_empty, ensure_seed_sources
from backend.app.engine.scoring import validate_scoring_weights_on_startup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    logger.info(
        "LLM configuration loaded: configured=%s model=%s base_url=%s",
        bool(settings.llm_api_key),
        settings.llm_model,
        safe_llm_base_url(settings.llm_base_url),
    )
    validate_scoring_weights_on_startup(logger)
    init_db()
    db = SessionLocal()
    try:
        ensure_auth_defaults(db)
        ensure_seed_sources(db)
        ensure_seed_products_if_empty(db)
    finally:
        db.close()
    if not settings.disable_scheduler_in_tests:
        init_scheduler()
    yield

app = FastAPI(
    title="智能保险推荐引擎",
    description="Smart Insurance Recommendation System",
    version="1.0.0",
    lifespan=lifespan,
)

cors_allow_origins = [
    origin.strip()
    for origin in settings.cors_allow_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)

app.include_router(products_router)
app.include_router(recommend_router)
app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {"message": "智能保险推荐引擎已启动", "version": "1.0.0"}
