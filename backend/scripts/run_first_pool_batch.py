"""本地/一次性：驱动首批真实产品池抓取（发现 → 抓取 → 抽取 → 自动发布）。

不是定时任务的一部分；生产由 scheduler.run_product_pool_maintenance 定期执行。
用法：python backend/scripts/run_first_pool_batch.py [--max-new 5] [--jobs N]
"""
import argparse
import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import backend.app.models.auth  # noqa: F401  注册全部 ORM mapper
import backend.app.models.benefit  # noqa: F401
import backend.app.models.rule  # noqa: F401
from backend.app.database import SessionLocal, init_db
from backend.app.data_ingestion.discovery import run_discovery_all
from backend.app.data_ingestion.pipelines.crawl_product import execute_crawl_job
from backend.app.data_ingestion.pipeline import ensure_seed_sources
from backend.app.models.data_ingestion import CrawlJob, CrawlRun, ProductDraft
from backend.app.models.product import Product


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=5, help="每源本次最多新建产品页")
    parser.add_argument("--jobs", type=int, default=5, help="本次最多执行的抓取任务数")
    args = parser.parse_args()

    os.environ["DISCOVERY_MAX_NEW_PER_SOURCE"] = str(args.max_new)

    db = SessionLocal()
    try:
        init_db()
        ensure_seed_sources(db)
        print("== discovery ==")
        for result in run_discovery_all(db):
            print(result)

        jobs = (
            db.query(CrawlJob)
            .filter(CrawlJob.status == "enabled")
            .order_by(CrawlJob.id.desc())
            .limit(args.jobs)
            .all()
        )
        print(f"== crawling {len(jobs)} jobs ==")
        for job in jobs:
            t0 = time.time()
            try:
                run = execute_crawl_job(db, job)
                print(f"job {job.id}: {run.status} http={run.http_status} ({time.time() - t0:.1f}s) {run.error_message or ''}")
            except Exception as exc:
                print(f"job {job.id}: CRASH {exc}")

        print("== drafts ==")
        for draft in db.query(ProductDraft).order_by(ProductDraft.id.desc()).limit(20):
            data = draft.draft_data or {}
            print(f"draft {draft.id} [{draft.status}] conf={draft.confidence:.2f} "
                  f"{data.get('name', '?')[:30]} | {data.get('company', '?')} | {data.get('type', '?')} | "
                  f"prem={data.get('premium_min')}-{data.get('premium_max')} | {data.get('source_url', '')[:60]}")

        print("== on-shelf products ==")
        for product in db.query(Product).filter(Product.status == 1).all():
            print(f"#{product.id} {product.company} {product.name} | {product.type} | {product.source_url[:70]}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
