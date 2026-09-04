"""Esquemas de entrada del operador (§5)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GPS(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None = None
    mocked: bool = False
    at: datetime | None = None


class Photo(BaseModel):
    key: str
    base64: str


class OpenChecklist(BaseModel):
    cart_secure: bool
    battery_ok: bool
    product_ok: bool
    clean_ok: bool
    pos_ok: bool


class CloseChecklist(BaseModel):
    off_ok: bool = True
    clean_ok: bool = True
    secured_ok: bool = True
    stored_ok: bool = True
    charging_ok: bool = True


class ShiftOpenIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    assignment_id: uuid.UUID
    opened_at: datetime | None = None
    checklist: OpenChecklist
    gps: GPS | None = None
    photos: list[Photo] | None = None


class ShiftCloseIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    closed_at: datetime | None = None
    cash_counted_cents: int = Field(ge=0)
    product_counts: dict[uuid.UUID, int] = Field(default_factory=dict)
    checklist: CloseChecklist = Field(default_factory=CloseChecklist)
    gps: GPS | None = None
    photos: list[Photo] | None = None


class ShiftTransferIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    to_operator_id: uuid.UUID
    cash_counted_cents: int = Field(ge=0)
    product_counts: dict[uuid.UUID, int] = Field(default_factory=dict)
    gps: GPS | None = None
    occurred_at: datetime | None = None


class SaleLineIn(BaseModel):
    presentation_id: uuid.UUID
    qty: int = Field(ge=1, le=500)
    flavor_id: uuid.UUID | None = None


class PaymentIn(BaseModel):
    method: Literal["cash", "qr", "card"]
    amount_cents: int = Field(ge=0)


class SaleIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    shift_id: uuid.UUID
    occurred_at: datetime | None = None
    price_version_id: uuid.UUID
    lines: list[SaleLineIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(min_length=1)
    offline_created: bool = False
    gps: GPS | None = None


class SaleCancelIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    reason_code: str = Field(min_length=2, max_length=40)
    note: str | None = None


class WasteIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    shift_id: uuid.UUID
    occurred_at: datetime | None = None
    presentation_id: uuid.UUID
    qty: int = Field(ge=1, le=1000)
    reason_code: Literal["spill", "quality", "expired", "sample", "other"]
    note: str | None = None


class HelpCaseIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    shift_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    category: Literal["cart", "battery", "product", "payment", "security", "other"]
    note: str | None = None
    photo_base64: str | None = None
    gps: GPS | None = None


class ReceiptLineIn(BaseModel):
    presentation_id: uuid.UUID
    qty: int = Field(ge=1, le=10000)
    lot_code: str | None = None


class ReceiptIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    shift_id: uuid.UUID
    occurred_at: datetime | None = None
    qr_code: str | None = None
    lines: list[ReceiptLineIn] = Field(min_length=1)


class CountIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    shift_id: uuid.UUID
    occurred_at: datetime | None = None
    counts: dict[uuid.UUID, int]


class GpsPingIn(BaseModel):
    shift_id: uuid.UUID
    at: datetime | None = None
    lat: float
    lng: float
    accuracy_m: float | None = None
    mocked: bool = False
    battery_pct: int | None = Field(default=None, ge=0, le=100)


class GpsBatchIn(BaseModel):
    pings: list[GpsPingIn] = Field(min_length=1)


SyncType = Literal[
    "sale", "waste", "shift_open", "shift_close", "help_case", "gps_ping", "inventory_receipt", "inventory_count",
    "sale_cancel", "shift_transfer",
]


class SyncCommandIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    type: SyncType
    created_at: datetime | None = None
    payload: dict


class SyncBatchIn(BaseModel):
    device_id: str
    commands: list[SyncCommandIn]
