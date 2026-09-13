"""一次性数据修复：把按"元"误报的保额（sum_insured_min/max > 10000）÷10000。

背景：存储规范为 sum_insured_* 单位=万、premium_*/deductible 单位=元
（INS-003）。早期 LLM 提取口径把所有金额按"元"返回，300 万元保额被存成
3000000，用户侧会展示成"3000000万"。提取侧已在 product_schema 加防呆归一，
本脚本修复存量数据。

只修复「经摄取发布」的产品——存在 ProductVersion 发布记录；种子产品
（无 ProductVersion）的保额口径本就是万，跳过。每次修复写审计日志。
用法：python backend/scripts/fix_sum_insured_units.py [--dry-run]
"""
import argparse
import os
import sys

# DATABASE_URL 为相对路径（sqlite:///data/insurance.db），必须先定位到仓库根，
# 否则会在 backend/ 下误建空库导致 "no such table"。
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from backend.app.database import SessionLocal
from backend.app.models.data_ingestion import ProductVersion
from backend.app.models.product import Product
from backend.app.services.auth_service import write_audit_log

# 万；零售险种保额不可能超过 10 亿（10000 万），与 schema 防呆阈值一致
SUM_INSURED_LIMIT = 10000


def main() -> int:
    parser = argparse.ArgumentParser(description="把按元误报的保额 ÷10000（INS-003 一次性修复）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要修复的产品，不写库")
    args = parser.parse_args()

    db = SessionLocal()
    fixed = 0
    try:
        published_ids = {v.product_id for v in db.query(ProductVersion).all()}
        products = (
            db.query(Product).filter(Product.id.in_(published_ids)).all()
            if published_ids else []
        )
        for product in products:
            changes = {}
            for field in ("sum_insured_min", "sum_insured_max"):
                value = getattr(product, field)
                if value is not None and value > SUM_INSURED_LIMIT:
                    changes[field] = {"before": value, "after": value / 10000}
            if not changes:
                continue
            print(f"#{product.id} {product.company} {product.name}: {changes}")
            if args.dry_run:
                continue
            for field, change in changes.items():
                setattr(product, field, change["after"])
            write_audit_log(
                db, None, "data.fix_sum_insured_units", "product",
                resource_id=str(product.id), detail=changes,
            )
            fixed += 1
        if args.dry_run:
            db.rollback()
            print(f"dry-run done, nothing written")
        else:
            db.commit()
            print(f"done: {fixed} products fixed")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
