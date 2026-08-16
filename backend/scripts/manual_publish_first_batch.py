"""一次性：LLM 不可用期间的人工审核发布（TASK-034 首批真实产品）。

数据核对自开心保产品详情页（Playwright 抓取的真实页面文本，人工读取），
走正规审核链路：manual 草稿 → 人工 approve → Product/Rule/Benefit/Version。
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import backend.app.models.auth  # noqa: F401
import backend.app.models.benefit  # noqa: F401
import backend.app.models.rule  # noqa: F401
from backend.app.database import SessionLocal
from backend.app.data_ingestion.pipeline import (
    archive_raw_document,
    create_extraction_review,
    create_source_page,
    ensure_seed_sources,
)
from backend.app.data_ingestion.review import approve_review_task
from backend.app.crawler.scraper import fetch_page_text
from backend.app.models.data_ingestion import SourcePlatform
from backend.app.models.product import Product

PRODUCTS = [
    {
        "url": "https://www.kaixinbao.com/yiwai-baoxian/358178.shtml",
        "data": {
            "name": "中国人保大护甲8号意外险（高龄版）",
            "company": "人保财险",
            "type": "意外险",
            "premium_min": 228,
            "premium_max": 0,
            "sum_insured_min": 0,
            "sum_insured_max": 10,
            "coverage_period": "1年",
            "payment_period": "1年",
            "source_url": "https://www.kaixinbao.com/yiwai-baoxian/358178.shtml",
            "min_age": 0, "max_age": 85, "job_class_limit": 6,
            "waiting_period_days": 0,
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "意外身故伤残", "benefit_amount": "10万", "payment_limit": "基本保额"},
                {"benefit_type": "basic", "benefit_name": "意外医疗（含门急诊和住院）", "benefit_amount": "5万", "payment_limit": "不限医保"},
                {"benefit_type": "basic", "benefit_name": "意外住院津贴", "benefit_amount": "50元/天", "payment_limit": ""},
            ],
        },
    },
    {
        "url": "https://www.kaixinbao.com/jiankang-baoxian/357600.shtml",
        "data": {
            "name": "复星保德信大黄蜂16号少儿重疾险(旗舰版)",
            "company": "复星保德信人寿",
            "type": "重疾险",
            "premium_min": 490,
            "premium_max": 0,
            "sum_insured_min": 0,
            "sum_insured_max": 0,
            "coverage_period": "",
            "payment_period": "",
            "source_url": "https://www.kaixinbao.com/jiankang-baoxian/357600.shtml",
            "disease_count": 125,
            "min_age": 0, "max_age": 17, "job_class_limit": 6,
            "waiting_period_days": 180,
            "has_insured_waiver": True,
            "benefits": [
                {"benefit_type": "core", "benefit_name": "重大疾病保险金（125种）", "benefit_amount": "100%基本保额", "payment_limit": "等待期180天后"},
                {"benefit_type": "basic", "benefit_name": "中症疾病保险金", "benefit_amount": "60%基本保额", "payment_limit": ""},
            ],
        },
    },
]


def main() -> int:
    db = SessionLocal()
    try:
        ensure_seed_sources(db)
        platform = db.query(SourcePlatform).filter(SourcePlatform.name == "开心保").first()
        for item in PRODUCTS:
            url = item["url"]
            page = create_source_page(db, platform.id, url)
            text, html, status = fetch_page_text(url, timeout=30000)
            print(f"fetch {status} {url}")
            raw = archive_raw_document(db, page, text, html)
            task = create_extraction_review(db, raw, item["data"], confidence=0.95, extractor="manual_review")
            if task.status == "pending":
                approve_review_task(db, task, reviewer_id=None, note="人工审核发布：字段核对自来源页文本（LLM 暂不可用）")
            db.refresh(task)
            print(f"task {task.id} -> {task.status}")

        for product in db.query(Product).filter(Product.status == 1).all():
            print(f"#{product.id} {product.company} {product.name} | {product.type} | prem={product.premium_min} | {product.source_url}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
