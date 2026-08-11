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


def list_products(db: Session, product_type: str | None = None, status: int = 1,
                page: int = 1, page_size: int = 20, search: str | None = None) -> tuple[list[Product], int]:
    query = db.query(Product).filter(Product.status == status)
    if product_type:
        query = query.filter(Product.type == product_type)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%") | Product.company.ilike(f"%{search}%"))
    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()
    return products, total


def compare_products(db: Session, product_ids: list[int]) -> list[dict]:
    results = []
    for pid in product_ids:
        detail = get_product_with_details(db, pid)
        if detail:
            results.append(detail)
    return results


def create_product(db: Session, data: dict, commit: bool = True) -> Product:
    product = Product(
        name=data["name"],
        company=data["company"],
        type=data["type"],
        status=data.get("status", 1),
        premium_min=data.get("premium_min"),
        premium_max=data.get("premium_max"),
        sum_insured_min=data.get("sum_insured_min"),
        sum_insured_max=data.get("sum_insured_max"),
        coverage_period=data.get("coverage_period"),
        payment_period=data.get("payment_period"),
        source_url=data.get("source_url"),
        deductible=data.get("deductible"),
        disease_count=data.get("disease_count"),
        mild_disease_count=data.get("mild_disease_count"),
        moderate_disease_count=data.get("moderate_disease_count"),
        has_mild_coverage=data.get("has_mild_coverage", False),
        has_moderate_coverage=data.get("has_moderate_coverage", False),
        has_multi_claim=data.get("has_multi_claim", False),
        company_tier=data.get("company_tier", 2),
    )
    db.add(product)
    db.flush()

    rule_data = data.get("rule")
    if rule_data:
        rule = Rule(product_id=product.id, **rule_data)
        db.add(rule)

    benefits_data = data.get("benefits", [])
    for benefit_data in benefits_data:
        benefit = Benefit(product_id=product.id, **benefit_data)
        db.add(benefit)

    if commit:
        db.commit()
        db.refresh(product)
    else:
        db.flush()
    return product


def update_product(db: Session, product_id: int, data: dict, commit: bool = True) -> Product | None:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None

    product_fields = [
        "name", "company", "type", "status", "premium_min", "premium_max",
        "sum_insured_min", "sum_insured_max", "coverage_period", "payment_period",
        "source_url", "deductible", "disease_count", "mild_disease_count",
        "moderate_disease_count", "has_mild_coverage", "has_moderate_coverage",
        "has_multi_claim", "company_tier",
    ]
    for field in product_fields:
        if field in data:
            setattr(product, field, data[field])

    rule_data = data.get("rule")
    if rule_data:
        rule = db.query(Rule).filter(Rule.product_id == product_id).first()
        if rule:
            for key, value in rule_data.items():
                setattr(rule, key, value)
        else:
            rule = Rule(product_id=product_id, **rule_data)
            db.add(rule)

    benefits_data = data.get("benefits")
    if benefits_data is not None:
        db.query(Benefit).filter(Benefit.product_id == product_id).delete()
        for benefit_data in benefits_data:
            benefit = Benefit(product_id=product_id, **benefit_data)
            db.add(benefit)

    if commit:
        db.commit()
        db.refresh(product)
    else:
        db.flush()
    return product


def soft_delete_product(db: Session, product_id: int) -> bool:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return False
    product.status = 0
    db.commit()
    return True
