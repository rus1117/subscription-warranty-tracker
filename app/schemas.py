from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.security import validate_cancel_url

BillingCycleType = Literal["monthly", "yearly", "custom_days"]
SubscriptionStatusType = Literal["active", "paused", "cancelled"]


class SubscriptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(default="Общее", min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="RUB", min_length=1, max_length=10)
    billing_cycle: BillingCycleType = Field(default="monthly")
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    next_billing_date: date
    remind_days_before: int = Field(default=3, ge=0, le=365)
    status: SubscriptionStatusType = Field(default="active")
    cancel_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "category", "currency")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Поле не может быть пустым")
        return stripped

    @field_validator("cancel_url")
    @classmethod
    def _check_cancel_url(cls, value: str | None) -> str | None:
        return validate_cancel_url(value)

    @model_validator(mode="after")
    def _check_custom_days(self) -> "SubscriptionCreate":
        if self.billing_cycle == "custom_days":
            if self.cycle_days is None or self.cycle_days < 1:
                raise ValueError("Для произвольного цикла (custom_days) необходимо указать cycle_days >= 1")
        else:
            self.cycle_days = None
        return self


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    amount: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=1, max_length=10)
    billing_cycle: BillingCycleType | None = Field(default=None)
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    next_billing_date: date | None = None
    remind_days_before: int | None = Field(default=None, ge=0, le=365)
    status: SubscriptionStatusType | None = None
    cancel_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "category", "currency")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Поле не может быть пустым")
        return stripped

    @field_validator("cancel_url")
    @classmethod
    def _check_cancel_url(cls, value: str | None) -> str | None:
        return validate_cancel_url(value)


class SubscriptionStatusUpdate(BaseModel):
    status: SubscriptionStatusType


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    amount: float
    currency: str
    billing_cycle: str
    cycle_days: int | None
    next_billing_date: date
    remind_days_before: int
    status: str
    cancel_url: str | None
    notes: str | None
    days_until_billing: int
    monthly_equivalent: float
    yearly_equivalent: float
    is_due_soon: bool
    created_at: datetime


class WarrantyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_name: str
    store: str | None
    purchase_date: date
    warranty_end_date: date
    price: float
    currency: str
    serial_number: str | None
    receipt_filename: str | None
    receipt_original_name: str | None
    has_receipt: bool
    remind_days_before: int
    notes: str | None
    days_left: int
    is_expired: bool
    is_expiring_soon: bool
    created_at: datetime


class SummaryOut(BaseModel):
    monthly_total: float
    yearly_total: float
    active_subscriptions_count: int
    paused_subscriptions_count: int
    cancelled_subscriptions_count: int
    warranties_count: int
    active_warranties_count: int
    upcoming_subscriptions: list[SubscriptionOut]
    expiring_warranties: list[WarrantyOut]
    alerts_count: int


class NotificationCheckOut(BaseModel):
    checked_at: datetime
    upcoming_subscriptions: list[SubscriptionOut]
    expiring_warranties: list[WarrantyOut]
    alerts_count: int
    messages: list[str]
    telegram_configured: bool
    telegram_sent: bool
