from sqlalchemy.orm import Session
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit


def get_product_with_details(db: Session, product_id: int) -> dict | None:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None
    rule = db.query(Rule).filter(Rule.product_id == product_id).first()
    benefits = db.query(Benefit).filter(Benefit.product_id == product_id).all()
    return {
        "product": product,
        "rule": rule,
        "benefits": benefits,
    }


def list_products(db: Session, product_type: str | None = None, status: int = 1) -> list[Product]:
    query = db.query(Product).filter(Product.status == status)
    if product_type:
        query = query.filter(Product.type == product_type)
    return query.all()


def compare_products(db: Session, product_ids: list[int]) -> list[dict]:
    results = []
    for pid in product_ids:
        detail = get_product_with_details(db, pid)
        if detail:
            results.append(detail)
    return results
