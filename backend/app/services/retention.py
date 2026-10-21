"""Retention for saved recommendation records.

Recommendation records contain the user profile and the result, including
health declarations. `RECORD_RETENTION_DAYS` decides how long they are kept:

* `0` (default) keeps everything. This preserves the behaviour of deployments
  created before the setting existed.
* A positive value deletes records whose `created_at` is older than the cutoff.

The deletion is a hard delete of the database row; there is no soft-delete flag
and no archive. That is deliberate: a retained copy of health data after the
declared retention window would defeat the purpose. Operators who need an
archive must export before shortening the retention window.

Saved profiles (`saved_profiles`) are user-managed and are not touched here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from backend.app.models.auth import RecommendationRecord
from backend.app.time import utc_now


@dataclass(frozen=True)
class RetentionResult:
    enabled: bool
    retention_days: int
    cutoff: str | None
    matched: int
    deleted: int

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "retention_days": self.retention_days,
            "cutoff": self.cutoff,
            "matched": self.matched,
            "deleted": self.deleted,
        }


def purge_expired_recommendation_records(
    db: Session,
    retention_days: int,
    *,
    dry_run: bool = False,
) -> RetentionResult:
    """Delete recommendation records older than `retention_days`.

    `dry_run=True` counts what would be removed and changes nothing, so an
    operator can inspect the impact before running it for real.
    """
    if retention_days <= 0:
        return RetentionResult(False, retention_days, None, 0, 0)

    cutoff = utc_now() - timedelta(days=retention_days)
    query = db.query(RecommendationRecord).filter(RecommendationRecord.created_at < cutoff)
    matched = query.count()

    deleted = 0
    if matched and not dry_run:
        deleted = query.delete(synchronize_session=False)
        db.commit()

    return RetentionResult(
        enabled=True,
        retention_days=retention_days,
        cutoff=cutoff.isoformat(),
        matched=matched,
        deleted=deleted,
    )
