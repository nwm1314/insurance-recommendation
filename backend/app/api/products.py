from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.services.product_service import list_products, get_product_with_details, compare_products

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products")
def api_list_products(
    type: str | None = Query(None, alias="type"),
    db: Session = Depends(get_db),
):
    products = list_products(db, product_type=type)
    return {
        "products": [
            {
                "id": p.id, "name": p.name, "company": p.company,
                "type": p.type, "status": p.status,
                "premium_min": p.premium_min, "premium_max": p.premium_max,
                "sum_insured_max": p.sum_insured_max,
            }
            for p in products
        ]
    }


@router.get("/products/{product_id}")
def api_product_detail(product_id: int, db: Session = Depends(get_db)):
    detail = get_product_with_details(db, product_id)
    if not detail:
        raise HTTPException(status_code=404, detail="产品不存在")
    p = detail["product"]
    r = detail["rule"]
    return {
        "product": {
            "id": p.id, "name": p.name, "company": p.company, "type": p.type,
            "premium_min": p.premium_min, "premium_max": p.premium_max,
            "sum_insured_min": p.sum_insured_min, "sum_insured_max": p.sum_insured_max,
            "coverage_period": p.coverage_period, "payment_period": p.payment_period,
            "disease_count": p.disease_count,
            "has_mild_coverage": p.has_mild_coverage,
            "has_moderate_coverage": p.has_moderate_coverage,
            "has_multi_claim": p.has_multi_claim,
        },
        "rule": {
            "min_age": r.min_age, "max_age": r.max_age,
            "job_class_limit": r.job_class_limit,
            "waiting_period_days": r.waiting_period_days,
            "has_insured_waiver": r.has_insured_waiver,
            "has_insurer_waiver": r.has_insurer_waiver,
            "health_disclosure_count": r.health_disclosure_count,
        } if r else None,
        "benefits": [
            {
                "benefit_type": b.benefit_type, "benefit_name": b.benefit_name,
                "benefit_amount": b.benefit_amount, "payment_limit": b.payment_limit,
            }
            for b in detail["benefits"]
        ],
    }


@router.post("/compare")
def api_compare(product_ids: list[int], db: Session = Depends(get_db)):
    details = compare_products(db, product_ids)
    return {"comparison": [
        {
            "name": d["product"].name,
            "company": d["product"].company,
            "type": d["product"].type,
            "premium": f"{d['product'].premium_min}-{d['product'].premium_max}",
            "sum_insured": f"{d['product'].sum_insured_min}-{d['product'].sum_insured_max}",
            "benefits": [b.benefit_name for b in d["benefits"]],
        }
        for d in details
    ]}
