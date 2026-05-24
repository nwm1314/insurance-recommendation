import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.database import init_db
from backend.app.api.products import router as products_router
from backend.app.api.recommend import router as recommend_router
from backend.app.api.admin import router as admin_router
from backend.app.middleware.rate_limiter import RateLimiterMiddleware
from backend.app.crawler.scheduler import init_scheduler

app = FastAPI(
    title="智能保险推荐引擎",
    description="Smart Insurance Recommendation System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)

app.include_router(products_router)
app.include_router(recommend_router)
app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    os.makedirs("data", exist_ok=True)
    init_db()
    init_scheduler()


@app.get("/")
def root():
    return {"message": "智能保险推荐引擎已启动", "version": "1.0.0"}
