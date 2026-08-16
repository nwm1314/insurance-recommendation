"""High-confidence auto-publish gate for crawled product drafts.

Policy (TASK-034): drafts extracted by the LLM extractor that clear the
confidence threshold AND a field-completeness gate are published automatically
with an audit trail; everything else waits in the manual review queue. Safety
rules:

- heuristic/off-shelf-detector drafts never auto-publish a *new* product
  (off-shelf drafts may auto-publish only as an update of the exact same
  product - taking something off the shelf is the conservative direction);
- only exact name+company matches may be auto-updated. Fuzzy matches
  (e.g. 达尔文7号 vs 达尔文8号) go to manual review - auto-overwriting a
  different product with new data would corrupt the catalog;
- placeholder values (待审核产品 / 待审核 / 0 premium) block auto-publish.
"""
import logging
import re

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.data_ingestion.pipeline import _normalize_name
from backend.app.models.data_ingestion import ProductDraft, ProductReviewTask
from backend.app.services.auth_service import write_audit_log

logger = logging.getLogger(__name__)

PLACEHOLDER_NAMES = {"待审核产品", "待审核", ""}


def _is_exact_match(draft: ProductDraft, data: dict) -> bool:
    """True when the draft's matched product has the same normalized
    name+company (the pipeline's fuzzy fallback must not auto-apply)."""
    if draft.matched_product_id is None:
        return False
    from backend.app.models.product import Product

    db = Session.object_session(draft)
    matched = db.query(Product).filter(Product.id == draft.matched_product_id).first()
    if matched is None:
        return False
    return (
        _normalize_name(matched.name) == _normalize_name(data.get("name") or "")
        and _normalize_name(matched.company) == _normalize_name(data.get("company") or "")
    )


def evaluate_auto_publish(draft: ProductDraft, extractor: str) -> tuple[bool, str]:
    """Return (should_publish, reason). Never raises."""
    data = draft.draft_data or {}
    if not settings.auto_publish_enabled:
        return False, "disabled"

    # 停售是保守方向：停售检测器（非 LLM）的草稿只要精确匹配既有产品即可
    # 自动下架，避免死链产品继续被推荐。
    if data.get("off_shelf"):
        if draft.matched_product_id is None:
            return False, "off_shelf_without_match"
        if not _is_exact_match(draft, data):
            return False, "fuzzy_match_needs_review"
        return True, "off_shelf_exact_match"

    if extractor != "llm":
        return False, "extractor_not_llm"

    if draft.confidence < settings.auto_publish_confidence:
        return False, "confidence_below_threshold"
    if (data.get("name") or "").strip() in PLACEHOLDER_NAMES:
        return False, "placeholder_name"
    if (data.get("company") or "").strip() in PLACEHOLDER_NAMES:
        return False, "placeholder_company"
    if not data.get("source_url"):
        return False, "missing_source_url"
    if not data.get("premium_min"):
        return False, "missing_premium"
    if not data.get("sum_insured_max"):
        return False, "missing_sum_insured"
    # 险种经 schema 归一化后总是合法枚举，但页面不是产品详情页时 LLM 可能
    # 硬凑；要求 URL 与发现模式一致由调度侧保证，这里只拦明显占位。
    if draft.matched_product_id is not None and not _is_exact_match(draft, data):
        return False, "fuzzy_match_needs_review"
    return True, "high_confidence_llm"


def try_auto_publish(db: Session, task: ProductReviewTask, draft: ProductDraft, extractor: str) -> bool:
    """Auto-publish a fresh review task when the gate clears. Audit-logged.

    On any publish failure the draft stays pending for manual review.
    """
    should, reason = evaluate_auto_publish(draft, extractor)
    if not should:
        logger.info("auto-publish skipped for draft %s: %s", draft.id, reason)
        return False
    from backend.app.data_ingestion.review import approve_review_task

    try:
        approve_review_task(db, task, reviewer_id=None, note=f"auto-publish: {reason}")
    except Exception as exc:
        logger.exception("auto-publish failed for draft %s", draft.id)
        write_audit_log(
            db, None, "review.auto_publish_failed", "product_draft",
            resource_id=str(draft.id),
            detail={"reason": reason, "error": str(exc)[:500]},
        )
        return False
    write_audit_log(
        db, None, "review.auto_publish", "product_draft",
        resource_id=str(draft.id),
        detail={
            "reason": reason,
            "confidence": draft.confidence,
            "extractor": extractor,
            "product_id": draft.matched_product_id,
            "name": (draft.draft_data or {}).get("name"),
            "source_url": (draft.draft_data or {}).get("source_url"),
        },
    )
    return True
