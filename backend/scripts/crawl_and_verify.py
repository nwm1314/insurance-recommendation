"""Crawl insurance product pages and verify against DB records.

Strategy (approach C):
  1. Third-party platforms first (comparison/aggregator sites)
  2. Official company websites for missing fields
  3. LLM structured extraction from crawled text
  4. Verification: crawled data vs DB records, report discrepancies

Usage:
  py -3.12 backend/scripts/crawl_and_verify.py
  py -3.12 backend/scripts/crawl_and_verify.py --verify-only   # skip crawl, just verify DB
  py -3.12 backend/scripts/crawl_and_verify.py --product-id 5  # single product
"""
import argparse
import hashlib
import json
import sys
import os
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.database import init_db, SessionLocal
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit
from backend.app.models.page_log import PageLog


# ---- Scraper (Playwright) ----

def fetch_page_text(url: str, timeout: int = 30000) -> tuple[Optional[str], Optional[str]]:
    """Fetch page text and HTML using Playwright headless browser."""
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        print("  [SKIP] playwright/bs4 not installed")
        return None, None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            browser.close()
            return text[:12000], html
    except Exception as e:
        print(f"  [FAIL] Playwright: {e}")
        return None, None


# ---- LLM Extractor ----

EXTRACT_PROMPT = """你是保险产品信息提取器。从以下网页文本提取保险产品信息。

返回严格 JSON：
{
  "name": "产品全称",
  "company": "保险公司名称",
  "type": "医疗险/意外险/重疾险/定期寿险/防癌险/年金险",
  "premium_min": 0, "premium_max": 0,
  "sum_insured_min": 0, "sum_insured_max": 0,
  "coverage_period": "",
  "payment_period": "",
  "disease_count": 0, "mild_disease_count": 0, "moderate_disease_count": 0,
  "has_mild_coverage": false, "has_moderate_coverage": false, "has_multi_claim": false,
  "min_age": 0, "max_age": 100, "job_class_limit": 6,
  "waiting_period_days": 90,
  "has_insured_waiver": false, "has_insurer_waiver": false,
  "health_disclosure_count": 0,
  "health_requirements": [],
  "benefits": [
    {"benefit_type": "basic", "benefit_name": "", "benefit_amount": "", "payment_limit": ""}
  ]
}

规则：无法提取则填默认值。type 必须为枚举值。金额单位为元。"""


def extract_product(text: str, url: str) -> Optional[dict]:
    """Extract product info via LLM. Skip if no API key configured."""
    from backend.app.config import settings

    if not settings.llm_api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_read_timeout,
        )
        for attempt in range(settings.llm_max_retries):
            try:
                response = client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": EXTRACT_PROMPT},
                        {"role": "user", "content": text[:8000]},
                    ],
                    response_format={"type": "json_object"},
                    timeout=settings.llm_read_timeout,
                )
                content = response.choices[0].message.content
                result = json.loads(content)
                result["source_url"] = url
                return result
            except Exception as e:
                if attempt == settings.llm_max_retries - 1:
                    print(f"  [LLM FAIL] {e}")
                    return None
        return None
    except Exception as e:
        print(f"  [LLM INIT FAIL] {e}")
        return None


# ---- MD5 & Page Log ----

def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def update_page_log(db, product_id: int, url: str, md5_hash: str):
    existing = db.query(PageLog).filter(
        PageLog.product_id == product_id,
        PageLog.page_url == url,
    ).first()
    if existing:
        existing.page_md5_hash = md5_hash
        existing.last_checked = datetime.utcnow()
    else:
        db.add(PageLog(
            product_id=product_id,
            page_url=url,
            page_md5_hash=md5_hash,
            last_checked=datetime.utcnow(),
        ))
    db.commit()


# ---- Verification ----

def verify_product(crawled: dict, db_product: Product, db_rule: Rule) -> list[str]:
    """Compare crawled data against DB record. Returns discrepancy list."""
    issues = []

    checks = [
        ("name", "产品名称"),
        ("type", "险种"),
        ("company", "保险公司"),
    ]
    for field, label in checks:
        crawled_val = str(crawled.get(field, "")).strip()
        db_val = str(getattr(db_product, field, "")).strip()
        if crawled_val and db_val and crawled_val != db_val:
            issues.append(f"{label}: 爬取='{crawled_val}' vs DB='{db_val}'")

    # Premium range
    c_min = crawled.get("premium_min", 0) or 0
    c_max = crawled.get("premium_max", 0) or 0
    if c_min > 0 and db_product.premium_min:
        diff_pct = abs(c_min - db_product.premium_min) / max(db_product.premium_min, 1)
        if diff_pct > 0.3:
            issues.append(f"最低保费差异 {diff_pct:.0%}: 爬取={c_min} vs DB={db_product.premium_min}")

    # Sum insured
    c_si = crawled.get("sum_insured_max", 0) or 0
    if c_si > 0 and db_product.sum_insured_max:
        diff_pct = abs(c_si - db_product.sum_insured_max) / max(db_product.sum_insured_max, 1)
        if diff_pct > 0.3:
            issues.append(f"最高保额差异 {diff_pct:.0%}: 爬取={c_si} vs DB={db_product.sum_insured_max}")

    # Age range
    c_age_min = crawled.get("min_age", 0) or 0
    c_age_max = crawled.get("max_age", 0) or 0
    if c_age_min > 0 and db_rule.min_age and abs(c_age_min - db_rule.min_age) > 5:
        issues.append(f"最小年龄: 爬取={c_age_min} vs DB={db_rule.min_age}")
    if c_age_max > 0 and db_rule.max_age and abs(c_age_max - db_rule.max_age) > 5:
        issues.append(f"最大年龄: 爬取={c_age_max} vs DB={db_rule.max_age}")

    # Waiting period
    c_wait = crawled.get("waiting_period_days", 0) or 0
    if c_wait > 0 and db_rule.waiting_period_days:
        if abs(c_wait - db_rule.waiting_period_days) > 30:
            issues.append(f"等待期: 爬取={c_wait}天 vs DB={db_rule.waiting_period_days}天")

    return issues


# ---- Main ----

def crawl_all(verify_only: bool = False, product_id: Optional[int] = None):
    init_db()
    db = SessionLocal()

    query = db.query(Product).filter(Product.status == 1)
    if product_id:
        query = query.filter(Product.id == product_id)
    products = query.all()

    print(f"{'='*60}")
    print(f"保险产品爬取与校验")
    print(f"模式: {'仅校验' if verify_only else '爬取+校验'}")
    print(f"产品数: {len(products)}")
    print(f"{'='*60}\n")

    total_crawled = 0
    total_failed = 0
    total_issues = 0

    for p in products:
        rule = p.rules
        print(f"[{p.id}] {p.name} ({p.company})")
        print(f"     URL: {p.source_url}")

        if verify_only:
            # Just verify existing data (data integrity check)
            issues = []
            if not p.rules:
                issues.append("缺少投保规则")
            if not p.benefits:
                issues.append("缺少保障责任")
            if issues:
                for issue in issues:
                    print(f"  ✗ {issue}")
                total_issues += len(issues)
            else:
                print(f"  ✓ 数据完整")
            continue

        # Crawl
        text, html = fetch_page_text(p.source_url, timeout=20000)

        if not text:
            total_failed += 1
            print(f"  ✗ 页面无法访问（跳过）")
            continue

        # Record page fingerprint
        md5_hash = compute_md5(text)
        update_page_log(db, p.id, p.source_url, md5_hash)
        print(f"     MD5: {md5_hash[:12]}... 文本长度: {len(text)}")

        # LLM extraction
        crawled = extract_product(text, p.source_url)

        if not crawled:
            total_failed += 1
            print(f"  ✗ LLM 提取失败（跳过）")
            continue

        total_crawled += 1

        # Verify
        issues = verify_product(crawled, p, rule)
        if issues:
            total_issues += len(issues)
            print(f"  ⚠ 发现 {len(issues)} 处差异:")
            for issue in issues:
                print(f"     - {issue}")
        else:
            print(f"  ✓ 爬取数据与数据库一致")

    db.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"爬取完成")
    print(f"  成功爬取: {total_crawled}")
    print(f"  失败/跳过: {total_failed}")
    print(f"  数据差异: {total_issues} 处")
    print(f"{'='*60}")

    return total_crawled, total_failed, total_issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true", help="仅校验不爬取")
    parser.add_argument("--product-id", type=int, help="仅爬取指定产品")
    args = parser.parse_args()
    crawl_all(verify_only=args.verify_only, product_id=args.product_id)
