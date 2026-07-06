from sqlalchemy.orm import Session

from backend.app.time import utc_now
from backend.app.models.data_ingestion import ProductDraft, ProductReviewTask, ProductVersion


def approve_review_task(db: Session, task: ProductReviewTask, reviewer_id: int, note: str | None = None, product_id: int | None = None) -> ProductReviewTask:
    draft = db.query(ProductDraft).filter(ProductDraft.id == task.product_draft_id).first()
    if draft is None:
        raise ValueError("draft_not_found")

    task.status = "approved"
    task.reviewer_id = reviewer_id
    task.review_note = note
    task.reviewed_at = utc_now()
    draft.status = "approved"

    target_product_id = product_id or draft.matched_product_id
    if target_product_id:
        db.add(ProductVersion(
            product_id=target_product_id,
            product_draft_id=draft.id,
            version_data=draft.draft_data,
            published_by=reviewer_id,
        ))
        draft.status = "version_recorded"

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
