"""第三方测评佐证（TASK-035）：深蓝保测评文章的链接级关联。

边界（用户确认）：只存文章标题与 URL 做匹配佐证，不复制正文（版权安全）。
深蓝保无 robots.txt（OSS 404，按"不可达不硬拦"语义可抓），列表页
/pingce/list1..6 与文章页实测 200；文章标题结构规整：
「【产品名】保险公司 产品名怎么样？-险种-深蓝保」。

匹配规则：标题【】内产品名与产品名归一化互含，且标题险种标注与产品
险种一致（双信号，降低同系列产品误配）。
"""
import logging
import re

from sqlalchemy.orm import Session

from backend.app.data_ingestion.fetchers.page_fetcher import fetch_source_page
from backend.app.data_ingestion.pipeline import create_source_page
from backend.app.models.data_ingestion import SourcePlatform
from backend.app.models.product import Product
from backend.app.services.auth_service import write_audit_log

logger = logging.getLogger(__name__)

SHENLANBAO_LIST_URLS = [f"https://www.shenlanbao.com/pingce/list{i}" for i in range(1, 7)]

_ARTICLE_LINK = re.compile(r'<a[^>]+href=["\'](/pingce/(\d+))["\'][^>]*>\s*([^<]{4,120}?)\s*</a>')
_TITLE_NAME = re.compile(r"【([^【】]{2,40})】")
_TITLE_TYPE = re.compile(r"-(" + "|".join(["医疗险", "意外险", "重疾险", "定期寿险", "寿险", "防癌险", "年金险"]) + r")-")
# 列表页锚文本若为纯产品短名（实测形态：达尔文12号/大黄蜂17号（全能版）），
# 需排除"查看详情"等非产品锚文本
_NON_PRODUCT_ANCHORS = {"查看详情", "详情", "更多", "立即投保", "在线投保", "阅读全文", "了解详情"}


def _normalize(value: str) -> str:
    return re.sub(r"[\s（）()·\-—_]", "", value or "").upper()


def extract_articles(html: str) -> list[dict]:
    """从列表页 HTML 提取 (url, title) 并解析产品名/险种信号。

    标题带【】时取括号内为产品名（文章页形态）；否则锚文本本身即产品
    短名（列表页形态）。险种信号缺失时匹配端跳过险种校验。
    """
    articles: dict[str, dict] = {}
    for match in _ARTICLE_LINK.finditer(html or ""):
        path, article_id, title = match.group(1), match.group(2), match.group(3).strip()
        if article_id in articles:
            continue
        name_match = _TITLE_NAME.search(title)
        type_match = _TITLE_TYPE.search(title)
        product_name = name_match.group(1).strip() if name_match else title
        if not name_match and product_name in _NON_PRODUCT_ANCHORS:
            continue
        articles[article_id] = {
            "url": f"https://www.shenlanbao.com{path}",
            "title": title,
            "product_name": product_name,
            "insurance_type": type_match.group(1) if type_match else "",
        }
    return list(articles.values())


def match_article_for_product(product: Product, articles: list[dict]) -> dict | None:
    """名称互含 + 险种一致（双信号）；多候选取归一化相同优先、名称最长者。"""
    target = _normalize(product.name)
    if not target:
        return None
    best: dict | None = None
    best_score = -1
    for article in articles:
        article_name = _normalize(article.get("product_name") or "")
        if not article_name:
            continue
        if article_name not in target and target not in article_name:
            continue
        article_type = article.get("insurance_type") or ""
        if article_type and product.type and article_type != product.type and not (
            article_type == "寿险" and product.type == "定期寿险"
        ):
            continue
        exact = article_name == target
        score = (2 if exact else 0) + len(article_name)
        if score > best_score:
            best, best_score = article, score
    return best


def fetch_review_articles(db: Session) -> list[dict]:
    """抓取深蓝保测评列表页，返回带产品名/险种信号的文章池。"""
    platform = db.query(SourcePlatform).filter(SourcePlatform.name == "深蓝保").first()
    if platform is None:
        return []
    articles: dict[str, dict] = {}
    for list_url in SHENLANBAO_LIST_URLS:
        try:
            page = create_source_page(db, platform.id, list_url, page_type="review_entry")
            fetched = fetch_source_page(page)
            for article in extract_articles(fetched.html or ""):
                articles.setdefault(article["url"], article)
        except Exception as exc:
            logger.warning("shenlanbao list fetch failed %s: %s", list_url, exc)
    return list(articles.values())


def match_reviews_to_products(db: Session) -> dict:
    """为在售且尚无测评佐证的产品关联深蓝保测评文章（链接级）。"""
    products = db.query(Product).filter(
        Product.status == 1,
        Product.third_party_review_url.is_(None),
    ).all()
    if not products:
        return {"matched": 0, "candidates": 0}
    articles = fetch_review_articles(db)
    matched = 0
    for product in products:
        article = match_article_for_product(product, articles)
        if article is None:
            continue
        product.third_party_review_url = article["url"]
        product.third_party_review_title = article["title"][:200]
        matched += 1
    db.commit()
    write_audit_log(
        db, None, "verification.review_match", "product",
        detail={"products": len(products), "articles": len(articles), "matched": matched},
    )
    return {"matched": matched, "candidates": len(products), "articles": len(articles)}
