from sqlalchemy.orm import Session

from backend.app.time import utc_now
from backend.app.models.data_ingestion import ProductDraft, ProductReviewTask, ProductVersion

PRODUCT_FIELDS = [
    "name", "company", "type", "premium_min", "premium_max",
    "sum_insured_min", "sum_insured_max", "coverage_period", "payment_period",
    "source_url", "deductible", "disease_count", "mild_disease_count",
    "moderate_disease_count", "has_mild_coverage", "has_moderate_coverage",
    "has_multi_claim", "company_tier",
]
RULE_FIELDS = [
    "min_age", "max_age", "job_class_limit", "waiting_period_days",
    "has_insured_waiver", "has_insurer_waiver",
    "health_disclosure_count", "health_requirements",
]
BENEFIT_FIELDS = ["benefit_type", "benefit_name", "benefit_amount", "payment_limit", "desc"]
ZERO_IS_UNKNOWN = {"premium_min", "premium_max", "sum_insured_min", "sum_insured_max"}


def draft_data_to_product_payload(draft_data: dict) -> dict:
    """Convert a draft snapshot into the create/update payload shape used by
    backend.app.services.product_service (TASK-005)."""
    payload: dict = {}
    for key in PRODUCT_FIELDS:
        value = draft_data.get(key)
        if value is None:
            continue
        if key in ZERO_IS_UNKNOWN and value == 0:
            continue
        payload[key] = value
    rule = {key: draft_data[key] for key in RULE_FIELDS if draft_data.get(key) is not None}
    if rule:
        payload["rule"] = rule
    benefits = []
    for item in draft_data.get("benefits") or []:
        if not isinstance(item, dict) or not item.get("benefit_name"):
            continue
        benefits.append({key: item[key] for key in BENEFIT_FIELDS if item.get(key) is not None})
    if benefits:
        payload["benefits"] = benefits
    return payload


def approve_review_task(db: Session, task: ProductReviewTask, reviewer_id: int, note: str | None = None, product_id: int | None = None) -> ProductReviewTask:
    draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
    if draft is None:
        raise ValueError("draft_not_found")

    from backend.app.services.product_service import create_product, update_product

    target_product_id = product_id or draft.matched_product_id
    off_shelf = bool((draft.draft_data or {}).get("off_shelf"))

    if off_shelf and target_product_id is None:
        raise ValueError("off_shelf_draft_requires_match")

    # Product / Rule / Benefit write-back and the ProductVersion snapshot are
    # committed in a single transaction so a failed publish leaves no partial
    # catalog changes (both services run with commit=False here).
    if off_shelf or target_product_id is not None:
        if off_shelf:
            update_product(db, target_product_id, {"status": 0}, commit=False)
        else:
            update_product(db, target_product_id, draft_data_to_product_payload(draft.draft_data), commit=False)
    else:
        payload = draft_data_to_product_payload(draft.draft_data)
        if not payload.get("name") or not payload.get("company") or not payload.get("type"):
            raise ValueError("draft_incomplete_product_fields")
        product = create_product(db, payload, commit=False)
        target_product_id = product.id

    db.add(ProductVersion(
        product_id=target_product_id,
        product_draft_id=draft.id,
        version_data=draft.draft_data,
        published_by=reviewer_id,
    ))
    draft.status = "published"
    draft.matched_product_id = target_product_id
    task.status = "approved"
    task.reviewer_id = reviewer_id
    task.review_note = note
    task.reviewed_at = utc_now()
    db.commit()

    db.refresh(task)
    return task


def reject_review_task(db: Session, task: ProductReviewTask, reviewer_id: int, note: str | None = None) -> ProductReviewTask:
    draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
    task.status = "rejected"
    task.reviewer_id = reviewer_id
    task.review_note = note
    task.reviewed_at = utc_now()
    if draft:
        draft.status = "rejected"
    db.commit()
    db.refresh(task)
    return task


def rollback_product_version(db: Session, version: ProductVersion):
    """Restore the product to the state captured in a published version.

    Returns the restored Product. For off-shelf versions the product is
    reactivated; otherwise the full snapshot is written back.
    """
    from backend.app.services.product_service import update_product

    version_data = version.version_data or {}
    if version_data.get("off_shelf"):
        product = update_product(db, version.product_id, {"status": 1})
    else:
        product = update_product(db, version.product_id, draft_data_to_product_payload(version_data))
    if product is None:
        raise ValueError("product_not_found")
    return product
