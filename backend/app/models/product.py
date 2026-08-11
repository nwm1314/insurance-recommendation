from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=1)

    premium_min: Mapped[float] = mapped_column(Float, nullable=True)
    premium_max: Mapped[float] = mapped_column(Float, nullable=True)
    sum_insured_min: Mapped[float] = mapped_column(Float, nullable=True)
    sum_insured_max: Mapped[float] = mapped_column(Float, nullable=True)
    coverage_period: Mapped[str] = mapped_column(String(50), nullable=True)
    payment_period: Mapped[str] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=True)
    deductible: Mapped[float | None] = mapped_column(Float, nullable=True)

    disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    mild_disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    moderate_disease_count: Mapped[int] = mapped_column(Integer, nullable=True)
    has_mild_coverage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_moderate_coverage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_multi_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    company_tier: Mapped[int] = mapped_column(Integer, default=2)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    rules = relationship("Rule", back_populates="product", uselist=False)
    benefits = relationship("Benefit", back_populates="product")
