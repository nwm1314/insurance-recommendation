"""Purge recommendation records past the configured retention window.

REC-006: `RECORD_RETENTION_DAYS` used to be configuration-only. This script is
the manual counterpart of the daily scheduler job, for operators who do not run
the embedded scheduler (for example, replicas with `SCHEDULER_DISABLED=true`) or
who want to inspect the impact before deleting anything.

Usage:
    python backend/scripts/purge_expired_records.py --dry-run
    python backend/scripts/purge_expired_records.py
    python backend/scripts/purge_expired_records.py --days 365
    python backend/scripts/purge_expired_records.py --days 0    # no-op, keep forever

The deletion is a hard delete. Export the data first if you need an archive.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.services.retention import purge_expired_recommendation_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete recommendation records older than the retention window.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="retention window in days; defaults to RECORD_RETENTION_DAYS (0 = keep forever)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report how many records would be deleted without deleting them",
    )
    args = parser.parse_args()

    days = settings.record_retention_days if args.days is None else args.days
    if days < 0:
        print("retention days must be >= 0 (0 = keep forever)", file=sys.stderr)
        return 2

    # Verifies the schema before touching data: a stale database is a hard error
    # here, exactly as it is at application startup.
    init_db()

    db = SessionLocal()
    try:
        result = purge_expired_recommendation_records(db, days, dry_run=args.dry_run)
    finally:
        db.close()

    print(json.dumps({**result.as_dict(), "dry_run": args.dry_run}, indent=2))
    if not result.enabled:
        print(
            "retention is disabled (0 = keep forever); pass --days N to run a one-off cleanup",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
