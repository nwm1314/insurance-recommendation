"""官方来源交叉验证（TASK-035）。

两类独立证据，均只做"标注"（不影响在售/推荐/自动发布门槛）：

1. 官网补充验证（L2 存在性）：产品名能在承保公司官网的产品目录页中找到
   即视为 verified。逐站 adapter——只有产品目录服务端可抓的官网可验证
   （robots 明确允许），其余公司如实标记 unverifiable。不做保费字段级
   比对（官网保费为按年龄交互测算，无静态数据）。

2. 双聚合站交叉印证：同一产品被 >=2 个独立聚合站（不同平台）收录并经
   发布流程确认，即 dual_source_verified=True。
"""
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.data_ingestion.fetchers.page_fetcher import fetch_source_page
from backend.app.data_ingestion.pipeline import create_source_page
from backend.app.time import utc_now
from backend.app.models.data_ingestion import (
    ExtractionRun,
    ProductDraft,
    RawDocument,
    SourcePage,
    SourcePlatform,
)
from backend.app.models.product import Product
from backend.app.services.auth_service import write_audit_log

logger = logging.getLogger(__name__)

VERIFIED = "verified"
NOT_FOUND = "not_found"
UNVERIFIABLE = "unverifiable"
UNVERIFIED = "unverified"

# 官网验证 adapter：仅收录产品目录服务端可抓且 robots 允许的官网。
# 2026-08-16 实测：泰康在线 tk.cn robots `Allow: /`，/product/ 服务端渲染
# 含真实产品名；其余官网（国寿/泰康集团/众安/信泰等）产品列表为 JS 深度
# 渲染或 robots 禁抓，标记 unverifiable。
OFFICIAL_SITE_ADAPTERS = {
    "泰康在线": {
        "platform_name": "泰康在线官网",
        "listing_url": "https://www.tk.cn/product/",
    },
}


def _normalize(value: str) -> str:
    return re.sub(r"[\s（）()·\-—_]", "", value or "").upper()


def _extract_official_names(text: str) -> list[str]:
    """从官网产品目录文本提取候选产品名（保险产品命名特征词）。"""
    raw = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:险|保|福|康|鑫|护|盈)(?:[（(][^）)]{1,14}[）)])?", text or "")
    unique: list[str] = []
    for name in raw:
        if 3 <= len(name) <= 24 and name not in unique:
            unique.append(name)
    return unique


def _name_matches(product_name: str, official_names: list[str]) -> bool:
    """聚合站产品名与官网目录名常互为简称/全称（如 全能保 vs 泰康全能保2026），
    归一化后双向包含且长度差可控即视为同一产品。"""
    target = _normalize(product_name)
    if not target:
        return False
    for official in official_names:
        normalized = _normalize(official)
        if not normalized:
            continue
        if normalized in target or target in normalized:
            return True
    return False


def verify_product_official(db: Session, product: Product) -> str:
    """对单个产品执行官网验证并落库，返回新状态。"""
    adapter = OFFICIAL_SITE_ADAPTERS.get(product.company)
    if adapter is None:
        product.official_verification_status = UNVERIFIABLE
        db.commit()
        return UNVERIFIABLE

    platform = (
        db.query(SourcePlatform)
        .filter(SourcePlatform.name == adapter["platform_name"])
        .first()
    )
    if platform is None:
        product.official_verification_status = UNVERIFIABLE
        db.commit()
        return UNVERIFIABLE

    page = create_source_page(db, platform.id, adapter["listing_url"], page_type="verification_entry")
    try:
        fetched = fetch_source_page(page)
        names = _extract_official_names(fetched.text or "")
        if _name_matches(product.name, names):
            product.official_verification_status = VERIFIED
            product.official_verification_url = adapter["listing_url"]
            product.official_verified_at = datetime.utcnow()
        else:
            product.official_verification_status = NOT_FOUND
    except Exception as exc:
        # 网络/robots 失败不改状态（保持 unverified，下一轮维护重试）
        logger.warning("official verification fetch failed for product %s: %s", product.id, exc)
        return UNVERIFIED
    db.commit()
    return product.official_verification_status


def run_official_verifications(db: Session, batch: int = 10) -> dict:
    """维护任务钩子：每轮只验证少量 unverified 产品，避免一轮打爆官网。"""
    if not getattr(settings, "official_verification_enabled", True):
        return {"skipped": "disabled"}
    products = (
        db.query(Product)
        .filter(Product.status == 1, Product.official_verification_status == UNVERIFIED)
        .order_by(Product.id)
        .limit(batch)
        .all()
    )
    results = {VERIFIED: 0, NOT_FOUND: 0, UNVERIFIABLE: 0}
    for product in products:
        status = verify_product_official(db, product)
        if status in results:
            results[status] += 1
    if products:
        write_audit_log(
            db, None, "verification.official_run", "product",
            detail={"checked": len(products), **results},
        )
    return {"checked": len(products), **results}


# ------------------------------------------------------------ 双源交叉

def compute_dual_source(db: Session, product_id: int) -> bool:
    """产品被 >=2 个独立聚合站平台收录并发布 → dual_source_verified。

    判定链：published draft（matched 到该产品）→ extraction_run →
    raw_document → source_page → platform，统计不同 third_party 平台数。
    """
    rows = (
        db.query(SourcePlatform.name)
        .join(SourcePage, SourcePage.platform_id == SourcePlatform.id)
        .join(RawDocument, RawDocument.source_page_id == SourcePage.id)
        .join(ExtractionRun, ExtractionRun.raw_document_id == RawDocument.id)
        .join(ProductDraft, ProductDraft.extraction_run_id == ExtractionRun.id)
        .filter(
            ProductDraft.matched_product_id == product_id,
            ProductDraft.status == "published",
            # 仅产品数据源参与交叉（third_party）；深蓝保（third_party_review）
            # 是测评佐证源，不构成独立数据源印证
            SourcePlatform.platform_type == "third_party",
        )
        .distinct()
        .all()
    )
    return len({row[0] for row in rows}) >= 2


def refresh_dual_source(db: Session, product_id: int) -> bool:
    value = compute_dual_source(db, product_id)
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is not None and product.dual_source_verified != value:
        product.dual_source_verified = value
        db.commit()
    return value
