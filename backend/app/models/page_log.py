from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.database import Base


class PageLog(Base):
    __tablename__ = "page_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    page_md5_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    last_checked: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
