"""一次性数据修复：下架初始 seed 演示产品（TASK-034 产品池策略）。

产品池改为真实数据源（聚合站抓取 + 审核发布）后，seed 的 165 个虚构产品
不再参与推荐。带 ProductVersion 发布记录（抓取/审核发布）的产品是真实
数据，不受影响。

下架 = status 0（软删除，可追溯可回滚），不物理删除：
- 历史推荐记录的 JSON 快照不依赖 products 行，但保留行更利于追溯；
- rule_engine 对 inactive 产品显式拒绝（reason_code=inactive）。

用法：python backend/scripts/offshelf_seed_products.py [--dry-run]
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from backend.app.database import SessionLocal
# 注册全部 ORM 模型：Product 的 relationship("Rule"/"Benefit") 需要
# 对应 mapper 先进入 registry，否则查询触发 mapper 配置时解析失败。
import backend.app.models.auth  # noqa: F401
import backend.app.models.benefit  # noqa: F401
import backend.app.models.rule  # noqa: F401
from backend.app.models.data_ingestion import ProductVersion
from backend.app.models.product import Product


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        published_ids = {v.product_id for v in db.query(ProductVersion).all()}
        seeds = [
            p for p in db.query(Product).all()
            if p.id not in published_ids and p.status == 1
        ]
        print(f"seed products on shelf: {len(seeds)} (published/real untouched: {len(published_ids)})")
        if dry_run:
            for p in seeds[:10]:
                print(f"  would off-shelf #{p.id} {p.company} {p.name}")
            print("dry run, nothing changed")
            return 0
        for p in seeds:
            p.status = 0
        db.commit()
        print(f"done: {len(seeds)} seed products off-shelf (status=0)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
