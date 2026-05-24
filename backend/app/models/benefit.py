from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


class Benefit(Base):
    __tablename__ = "benefits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)

    benefit_type: Mapped[str] = mapped_column(String(50), default="basic")
    benefit_name: Mapped[str] = mapped_column(String(200), nullable=False)
    benefit_amount: Mapped[str] = mapped_column(String(200), nullable=True)
    payment_limit: Mapped[str] = mapped_column(String(200), nullable=True)
    desc: Mapped[str] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="benefits")
