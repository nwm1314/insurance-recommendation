"""一次性：人工审核发布「达尔文12号」（LLM 不可用期间，数据核对自开心保
真实产品页），随后执行官网验证与深蓝保测评匹配，端到端演示 TASK-035。"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import backend.app.models.auth  # noqa: F401
import backend.app.models.benefit  # noqa: F401
import backend.app.models.rule  # noqa: F401
from backend.app.database import SessionLocal
from backend.app.crawler.scraper import fetch_page_text
from backend.app.data_ingestion.pipeline import (
    archive_raw_document,
    create_extraction_review,
    create_source_page,
    ensure_seed_sources,
)
from backend.app.data_ingestion.review import approve_review_task
from backend.app.data_ingestion.review_evidence import match_reviews_to_products
from backend.app.models.data_ingestion import SourcePlatform
from backend.app.models.product import Product

URL = "https://www.kaixinbao.com/jiankang-baoxian/357645.shtml"
DATA = {
    "name": "达尔文12号重大疾病保险",
    "company": "信泰人寿",
    "type": "重疾险",
    "premium_min": 671,
    "premium_max": 0,
    "sum_insured_min": 0,
    "sum_insured_max": 0,
    "coverage_period": "终身",
    "payment_period": "趸交/5/10/20/30年",
    "source_url": URL,
    "disease_count": 120,
    "min_age": 0, "max_age": 60, "job_class_limit": 6,
    "waiting_period_days": 180,
    "benefits": [
        {"benefit_type": "core", "benefit_name": "重大疾病保险金（120种）", "benefit_amount": "100%基本保额", "payment_limit": "等待期180天后"},
    ],
}


def main() -> int:
    db = SessionLocal()
    try:
        ensure_seed_sources(db)
        platform = db.query(SourcePlatform).filter(SourcePlatform.name == "开心保").first()
        page = create_source_page(db, platform.id, URL)
        text, html, status = fetch_page_text(URL, timeout=30000)
        print("fetch:", status)
        raw = archive_raw_document(db, page, text, html)
        task = create_extraction_review(db, raw, DATA, confidence=0.95, extractor="manual_review")
        if task.status == "pending":
            approve_review_task(db, task, reviewer_id=None,
                                note="人工审核发布：字段核对自来源页（投保年龄上限按页面片段宽泛录入，以核保为准）")
        db.refresh(task)
        print("publish task:", task.status)

        result = match_reviews_to_products(db)
        print("shenlanbao match:", result)
        for p in db.query(Product).filter(Product.status == 1).all():
            print(f"#{p.id} {p.name[:26]} | 官网:{p.official_verification_status} | 双源:{p.dual_source_verified} "
                  f"| 测评:{p.third_party_review_title or '-'} -> {p.third_party_review_url or '-'}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
