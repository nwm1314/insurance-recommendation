import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.config import ensure_no_wildcard_with_credentials, safe_llm_base_url, settings
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
    # OPS-002 / PROD-002：未配置加密密钥时推荐记录明文落库——显式降级，不静默。
    # 推荐记录含 health_status / health_issues（敏感个人信息），故在生产环境下
    # 升级为 error 级并指明处置方式；本地/测试仍保持可用（不拒绝启动，否则会破坏
    # 开发体验与既有测试对 fail-open 语义的依赖）。
    if not settings.record_encryption_key:
        if settings.app_env == "production":
            logger.error(
                "RECORD_ENCRYPTION_KEY is not set while APP_ENV=production: recommendation "
                "records (profile/result, including health disclosures) are being stored in "
                "PLAINTEXT. This is a sensitive-personal-information compliance risk. "
                "Set RECORD_ENCRYPTION_KEY in .env and restart (see docs/docker-deployment.md, "
                "章节「推荐记录加密」)."
            )
        else:
            logger.warning(
                "RECORD_ENCRYPTION_KEY is not set: recommendation records (profile/result, "
                "including health disclosures) will be stored in PLAINTEXT. Set the key in .env "
                "before exposing the system to real users."
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

cors_allow_origins = settings.parsed_cors_origins
ensure_no_wildcard_with_credentials(cors_allow_origins, allow_credentials=True)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security response headers; HSTS is only emitted for production."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if settings.security_headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            if settings.app_env == "production" and settings.hsts_enabled:
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(products_router)
app.include_router(recommend_router)
app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {"message": "智能保险推荐引擎已启动", "version": "1.0.0"}
