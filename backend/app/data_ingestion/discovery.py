"""Product URL discovery: aggregator listing pages -> product detail crawl jobs.

Strategy: aggregator sites (huize, kaixinbao, ...) are the primary source of
real product data. Each configured source declares entry pages (robots-checked
listing pages) and a detail-URL pattern; discovery fetches the entries, extracts
matching product URLs and registers a SourcePage + CrawlJob for every new one.

Sites whose robots.txt disallows crawling (e.g. zhongmin.cn `Disallow: /`) are
not configured here on purpose.
"""
import logging
import re
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.data_ingestion.fetchers.page_fetcher import fetch_source_page
from backend.app.data_ingestion.pipeline import create_crawl_job, create_source_page
from backend.app.models.data_ingestion import CrawlJob, SourcePage, SourcePlatform
from backend.app.services.auth_service import write_audit_log

logger = logging.getLogger(__name__)

TRACKING_PARAM_PREFIXES = ("utm_", "spm", "channel", "from", "trace")


def _strip_tracking_params(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(TRACKING_PARAM_PREFIXES)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _canonical_huize(url: str) -> str:
    """慧择产品身份由 prodId 决定；planId/投放参数一律剥掉，避免同一产品重复建源。"""
    parts = urlsplit(url)
    match = re.search(r"(?:^|&)prodId=(\d+)", parts.query or "")
    if not match:
        return _strip_tracking_params(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, f"prodId={match.group(1)}", ""))


# detail_pattern 只匹配各站真实的产品详情页形态；entry 页均经 robots 校验。
DISCOVERY_SOURCES = [
    {
        "platform_name": "慧择网",
        "entries": ["https://www.huize.com/"],
        "detail_pattern": r"^https?://([\w-]+\.)*huize\.com/apps/cps/index/product/detail\?prodId=\d+$",
        "canonicalize": _canonical_huize,
    },
    {
        "platform_name": "开心保",
        "entries": ["https://www.kaixinbao.com/"],
        # 只收六险种形态（健康/意外/人寿/重疾/防癌/年金）；旅游险、车险等
        # 站内其他品类不属于产品池范围。
        "detail_pattern": r"^https?://([\w-]+\.)*kaixinbao\.com/(jiankang|yiwai|renshou|zhongji|fangai|nianjin)-baoxian/\d+\.shtml$",
        "canonicalize": lambda url: urlunsplit((*urlsplit(url)[:3], "", "")),
    },
]


def _normalize_href(base_url: str, href: str) -> str:
    href = href.strip()
    if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
        return ""
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    # query 保留（慧择的产品身份在 prodId query 参数里），跟踪参数清理交给
    # 各源的 canonicalize。
    return absolute


def extract_detail_urls(html: str, base_url: str, detail_pattern: str, canonicalize=None) -> list[str]:
    """Extract absolute, de-duplicated product detail URLs from listing HTML."""
    pattern = re.compile(detail_pattern)
    canonicalize = canonicalize or _strip_tracking_params
    found: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r'href=["\']([^"\']+)["\']', html or ""):
        url = _normalize_href(base_url, raw.replace("&amp;", "&"))
        if not url:
            continue
        url = canonicalize(url)
        if url in seen or not pattern.match(url):
            continue
        seen.add(url)
        found.append(url)
    return found


def discover_products_for_platform(db: Session, source: dict) -> dict:
    """Register crawl jobs for new product URLs found on one platform's entries.

    Returns {discovered, created, skipped_existing, errors}. Failures on one
    entry (robots block, fetch error) do not abort the rest.
    """
    platform = db.query(SourcePlatform).filter(SourcePlatform.name == source["platform_name"]).first()
    if platform is None:
        return {"discovered": 0, "created": 0, "skipped_existing": 0, "errors": [f"platform_not_found:{source['platform_name']}"]}

    pattern = source["detail_pattern"]
    discovered: list[str] = []
    errors: list[str] = []
    for entry_url in source["entries"]:
        try:
            entry_page = create_source_page(db, platform.id, entry_url, page_type="discovery_entry")
            fetched = fetch_source_page(entry_page)
            discovered.extend(extract_detail_urls(fetched.html or "", entry_url, pattern, source.get("canonicalize")))
        except Exception as exc:
            errors.append(f"{entry_url}: {exc}")
            logger.warning("discovery entry failed for %s: %s", entry_url, exc)

    created = 0
    skipped = 0
    cap = max(settings.discovery_max_new_per_source, 0)
    for url in discovered:
        existing = (
            db.query(SourcePage)
            .filter(SourcePage.platform_id == platform.id, SourcePage.url == url)
            .first()
        )
        if existing is not None:
            skipped += 1
            continue
        if created >= cap:
            break
        page = create_source_page(db, platform.id, url, page_type="product")
        job = db.query(CrawlJob).filter(CrawlJob.source_page_id == page.id).first()
        if job is None:
            create_crawl_job(db, f"{platform.name} 产品页 {page.id}", page.id)
        created += 1

    return {"discovered": len(discovered), "created": created, "skipped_existing": skipped, "errors": errors}


def run_discovery_all(db: Session) -> list[dict]:
    """Run discovery for every configured source; audit-logged per run."""
    if not settings.discovery_enabled:
        return []
    results = []
    for source in DISCOVERY_SOURCES:
        result = discover_products_for_platform(db, source)
        results.append({"platform": source["platform_name"], **result})
        write_audit_log(
            db, None, "discovery.run", "source_platform",
            resource_id=source["platform_name"],
            detail={k: v for k, v in result.items() if k != "errors"} | {"errors": result["errors"][:5]},
        )
    return results
