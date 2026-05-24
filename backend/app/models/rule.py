from sqlalchemy import String, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), unique=True, nullable=False)

    min_age: Mapped[int] = mapped_column(Integer, default=0)
    max_age: Mapped[int] = mapped_column(Integer, default=100)
    job_class_limit: Mapped[int] = mapped_column(Integer, default=6)

    waiting_period_days: Mapped[int] = mapped_column(Integer, default=90)
    has_insured_waiver: Mapped[bool] = mapped_column(Boolean, default=False)
    has_insurer_waiver: Mapped[bool] = mapped_column(Boolean, default=False)
    health_disclosure_count: Mapped[int] = mapped_column(Integer, default=0)
    health_requirements: Mapped[dict] = mapped_column(JSON, default=list)

    product = relationship("Product", back_populates="rules")
