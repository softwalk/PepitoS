"""Esquemas de entrada de supervisor / backoffice / admin."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str
    device_id: str = Field(min_length=4, max_length=120)
    device_name: str | None = None
    platform: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=200)
    device_id: str = Field(min_length=4, max_length=120)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordIn(BaseModel):
    new_password: str | None = None


class CorrectiveActionIn(BaseModel):
    description: str
    owner_id: uuid.UUID | None = None
    due_date: date | None = None


class AuditPhoto(BaseModel):
    key: str | None = None
    base64: str


class AuditIn(BaseModel):
    point_id: uuid.UUID
    shift_id: uuid.UUID | None = None
    checklist: dict[str, bool]
    cash_counted_cents: int | None = None
    notes: str | None = None
    photos: list[str | AuditPhoto] | None = None  # base64/data URL o {key, base64}
    corrective_actions: list[CorrectiveActionIn] = Field(default_factory=list)


class CasePatch(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    assignee_id: uuid.UUID | None = None
    resolution: str | None = None
    severity: Literal["urgent", "review", "normal"] | None = None
    category: str | None = None


class ActionPatch(BaseModel):
    status: Literal["pending", "done", "overdue"]


class RulePut(BaseModel):
    enabled: bool | None = None
    params: dict | None = None
    severity: Literal["urgent", "review", "normal"] | None = None


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


class ApprovalIn(BaseModel):
    approval_type: str = "payment"
    title: str
    amount_cents: int | None = None
    entity: str | None = None
    entity_id: uuid.UUID | None = None
    note: str | None = None


class MaintenanceTicketIn(BaseModel):
    asset_id: uuid.UUID
    title: str
    description: str | None = None
    severity: Literal["urgent", "review", "normal"] = "review"
    kind: Literal["corrective", "preventive"] = "corrective"
    evidence: list[str] | None = None


class MaintenanceTicketPatch(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    resolution: str | None = None
    severity: Literal["urgent", "review", "normal"] | None = None


class LotBlockIn(BaseModel):
    reason: str


# ---- Admin CRUD ----
class ZoneIn(BaseModel):
    name: str
    is_active: bool = True


class UserIn(BaseModel):
    username: str
    name: str
    role: Literal["operator", "supervisor", "ops", "finance", "admin"]
    password: str | None = None
    zone_id: uuid.UUID | None = None
    phone: str | None = None
    is_active: bool = True


class UserPatch(BaseModel):
    name: str | None = None
    role: Literal["operator", "supervisor", "ops", "finance", "admin"] | None = None
    password: str | None = None
    zone_id: uuid.UUID | None = None
    phone: str | None = None
    is_active: bool | None = None


class PointIn(BaseModel):
    name: str
    address: str | None = None
    lat: float
    lng: float
    geofence_radius_m: int = 150
    zone_id: uuid.UUID | None = None
    open_time: str | None = "08:00"
    close_time: str | None = "18:00"
    daily_target_cents: int | None = None  # None → settings.daily_sales_target_default_cents
    daily_target_tx: int = 60
    is_active: bool = True
    geo_verified: bool = True  # alta manual con coordenadas conocidas
    meta: dict | None = None


class PointPatch(BaseModel):
    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    geofence_radius_m: int | None = None
    zone_id: uuid.UUID | None = None
    open_time: str | None = None
    close_time: str | None = None
    daily_target_cents: int | None = None
    daily_target_tx: int | None = None
    is_active: bool | None = None
    geo_verified: bool | None = None
    meta: dict | None = None


class PointVerifyIn(BaseModel):
    verified: bool = True
    lat: float | None = None
    lng: float | None = None
    source: str | None = None  # p. ej. "GPS de apertura 04-sep 08:12"


class CartIn(BaseModel):
    code: str
    description: str | None = None
    is_active: bool = True


class CartPatch(BaseModel):
    code: str | None = None
    description: str | None = None
    is_active: bool | None = None


class AssignmentIn(BaseModel):
    operator_id: uuid.UUID
    point_id: uuid.UUID
    cart_id: uuid.UUID
    shift_date: date
    planned_start: datetime | None = None  # si no viene, se usa open_time del punto
    planned_end: datetime | None = None


class AssignmentPatch(BaseModel):
    operator_id: uuid.UUID | None = None
    point_id: uuid.UUID | None = None
    cart_id: uuid.UUID | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    status: str | None = None


class PresentationIn(BaseModel):
    name: str
    grams: int
    sort: int = 0
    is_active: bool = True
    product_id: uuid.UUID | None = None


class PresentationPatch(BaseModel):
    name: str | None = None
    grams: int | None = None
    sort: int | None = None
    is_active: bool | None = None


class PriceVersionIn(BaseModel):
    name: str
    valid_from: datetime | None = None
    prices: dict[uuid.UUID, int]


class PriceVersionPatch(BaseModel):
    is_active: bool | None = None
    name: str | None = None
    valid_to: datetime | None = None


class SettingPut(BaseModel):
    value: int | float | bool | str


class DevicePatch(BaseModel):
    name: str | None = None
    revoked: bool | None = None
    reason: str | None = None


class RevokeIn(BaseModel):
    reason: str | None = None
