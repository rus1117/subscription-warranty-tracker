from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Общее")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")
    billing_cycle: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    cycle_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    remind_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    cancel_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarrantyItem(Base):
    __tablename__ = "warranty_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    store: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    warranty_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")
    serial_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receipt_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remind_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
