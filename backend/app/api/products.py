from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal
from backend.app.database import get_db
from backend.app.dependencies.auth import get_client_ip, require_permission
from backend.app.models.auth import User
from backend.app.services.auth_service import write_audit_log
from backend.app.services.product_service import (
    list_products, get_product_with_details, compare_products,
    create_product, update_product, soft_delete_product,
)


class RuleIn(BaseModel):
    min_age: int = Field(default=0, ge=0, le=120)
    max_age: int = Field(default=100, ge=0, le=120)
    job_class_limit: int = Field(default=6, ge=1, le=6)
    waiting_period_days: int = Field(default=90, ge=0)
    has_insured_waiver: bool = False
    has_insurer_waiver: bool = False
    health_disclosure_count: int = Field(default=0, ge=0)
    health_requirements: list = Field(default_factory=list)


class BenefitIn(BaseModel):
    benefit_type: str = "basic"
    benefit_name: str = Field(min_length=1)
    benefit_amount: str | None = None
    payment_limit: str | None = None
    desc: str | None = None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=100)
    type: Literal["医疗险", "重疾险", "意外险", "定期寿险", "防癌险", "年金险"]
    status: int = Field(default=1, ge=0, le=1)
    premium_min: float | None = Field(default=None, ge=0)
    premium_max: float | None = Field(default=None, ge=0)
    sum_insured_min: float | None = Field(default=None, ge=0)
    sum_insured_max: float | None = Field(default=None, ge=0)
    coverage_period: str | None = None
    payment_period: str | None = None
    source_url: str | None = None
    deductible: float | None = Field(default=None, ge=0)
    disease_count: int | None = Field(default=None, ge=0)
    mild_disease_count: int | None = Field(default=None, ge=0)
    moderate_disease_count: int | None = Field(default=None, ge=0)
    has_mild_coverage: bool = False
    has_moderate_coverage: bool = False
    has_multi_claim: bool = False
    company_tier: int = Field(default=2, ge=1, le=3)
    rule: RuleIn | None = None
    benefits: list[BenefitIn] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=100)
    type: Literal["医疗险", "重疾险", "意外险", "定期寿险", "防癌险", "年金险"] | None = None
    status: int | None = Field(default=None, ge=0, le=1)
    premium_min: float | None = Field(default=None, ge=0)
    premium_max: float | None = Field(default=None, ge=0)
    sum_insured_min: float | None = Field(default=None, ge=0)
    sum_insured_max: float | None = Field(default=None, ge=0)
    coverage_period: str | None = None
    payment_period: str | None = None
    source_url: str | None = None
    deductible: float | None = Field(default=None, ge=0)
    disease_count: int | None = Field(default=None, ge=0)
    mild_disease_count: int | None = Field(default=None, ge=0)
    moderate_disease_count: int | None = Field(default=None, ge=0)
    has_mild_coverage: bool | None = None
    has_moderate_coverage: bool | None = None
    has_multi_claim: bool | None = None
    company_tier: int | None = Field(default=None, ge=1, le=3)
    rule: RuleIn | None = None
    benefits: list[BenefitIn] | None = None

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products")
def api_list_products(
    type: str | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    products, total = list_products(db, product_type=type, page=page, page_size=page_size, search=search)
    return {
        "products": [
            {
                "id": p.id, "name": p.name, "company": p.company,
                "type": p.type, "status": p.status,
                "premium_min": p.premium_min, "premium_max": p.premium_max,
                "sum_insured_max": p.sum_insured_max,
            }
            for p in products
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
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


def _serialize_product(p):
    return {
        "id": p.id, "name": p.name, "company": p.company,
        "type": p.type, "status": p.status,
        "premium_min": p.premium_min, "premium_max": p.premium_max,
        "sum_insured_min": p.sum_insured_min, "sum_insured_max": p.sum_insured_max,
        "coverage_period": p.coverage_period, "payment_period": p.payment_period,
        "deductible": p.deductible, "disease_count": p.disease_count,
        "mild_disease_count": p.mild_disease_count,
        "moderate_disease_count": p.moderate_disease_count,
        "has_mild_coverage": p.has_mild_coverage,
        "has_moderate_coverage": p.has_moderate_coverage,
        "has_multi_claim": p.has_multi_claim, "company_tier": p.company_tier,
        "source_url": p.source_url,
    }


@router.post("/products", status_code=201)
def api_create_product(
    payload: ProductCreate,
    request: Request,
    user: User = Depends(require_permission("product:write")),
    db: Session = Depends(get_db),
):
    product = create_product(db, payload.model_dump())
    write_audit_log(
        db, user, "product.create", "product", str(product.id),
        detail={"name": product.name, "company": product.company, "type": product.type},
        ip_address=get_client_ip(request),
    )
    return _serialize_product(product)


@router.put("/products/{product_id}")
def api_update_product(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    user: User = Depends(require_permission("product:write")),
    db: Session = Depends(get_db),
):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    product = update_product(db, product_id, data)
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    write_audit_log(
        db, user, "product.update", "product", str(product_id),
        detail={"updated_fields": sorted(data.keys())},
        ip_address=get_client_ip(request),
    )
    return _serialize_product(product)


@router.delete("/products/{product_id}")
def api_delete_product(
    product_id: int,
    request: Request,
    user: User = Depends(require_permission("product:write")),
    db: Session = Depends(get_db),
):
    if not soft_delete_product(db, product_id):
        raise HTTPException(status_code=404, detail="产品不存在")
    write_audit_log(
        db, user, "product.soft_delete", "product", str(product_id),
        detail={}, ip_address=get_client_ip(request),
    )
    return {"status": "ok", "message": "产品已停售"}
