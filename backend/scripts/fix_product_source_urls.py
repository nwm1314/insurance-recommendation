"""一次性数据修复：把早期 seed 编造的产品 source_url 重写为公司官网首页。

背景：旧版 seed 用「公司域名 + 编造的产品路径」拼接 source_url，且 8 个公司
域名本身是编造的（DNS 均无法解析），导致结果页产品链接 404/403。
seed.py 已改为只指向官网首页；本脚本把存量库中旧模式的 URL 重写对齐。

只重写「无 ProductVersion 发布记录」的产品——它们是初始 seed 写入的演示数据；
经抓取审核发布的产品（有 ProductVersion）保留其真实来源页 URL，不受影响。
用法：python backend/scripts/fix_product_source_urls.py [db_path]
"""
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
from backend.scripts.seed import COMPANY_URLS


def main() -> int:
    db = SessionLocal()
    updated = 0
    try:
        published_ids = {v.product_id for v in db.query(ProductVersion).all()}
        products = db.query(Product).all()
        for product in products:
            if product.id in published_ids:
                continue
            homepage = COMPANY_URLS.get(product.company)
            if not homepage or product.source_url == homepage:
                continue
            print(f"#{product.id} {product.company} {product.name}: {product.source_url} -> {homepage}")
            product.source_url = homepage
            updated += 1
        db.commit()
        print(f"done: {updated} products updated (published/crawled products untouched)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
