"""Turnos, GPS, checklists y sesiones de caja."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDMixin


class Shift(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "shifts"
    __table_args__ = (
        # Un carrito no puede tener dos turnos abiertos (§8)
        Index("uq_shifts_cart_open", "cart_id", unique=True, postgresql_where="status = 'open'"),
        # Un operador no puede tener dos turnos abiertos
        Index("uq_shifts_operator_open", "operator_id", unique=True, postgresql_where="status = 'open'"),
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assignments.id"))
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    cart_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("carts.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|closed|transferred
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_exceptions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    close_status: Mapped[str | None] = mapped_column(String(20))  # reconciled|difference
    cash_expected_cents: Mapped[int | None] = mapped_column(Integer)
    cash_counted_cents: Mapped[int | None] = mapped_column(Integer)
    difference_cents: Mapped[int | None] = mapped_column(Integer)
    product_diff: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transferred_to_shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    transferred_from_shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    open_gps: Mapped[dict | None] = mapped_column(JSONB)
    close_gps: Mapped[dict | None] = mapped_column(JSONB)

    operator: Mapped["User"] = relationship(foreign_keys=[operator_id])  # noqa: F821
    point: Mapped["Point"] = relationship()  # noqa: F821
    cart: Mapped["Cart"] = relationship()  # noqa: F821


class GpsPing(UUIDMixin, Base):
    __tablename__ = "gps_pings"
    __table_args__ = (Index("ix_gps_pings_shift_at", "shift_id", "at"),)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    device_id: Mapped[str | None] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    mocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    in_geofence: Mapped[bool | None] = mapped_column(Boolean)


class Checklist(UUIDMixin, Base):
    __tablename__ = "checklists"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # open|close
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ChecklistResult(UUIDMixin, Base):
    __tablename__ = "checklist_results"
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class CashSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cash_sessions"
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), unique=True, nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opening_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cash_sales_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    digital_sales_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_cents: Mapped[int | None] = mapped_column(Integer)
    counted_cents: Mapped[int | None] = mapped_column(Integer)
    difference_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|reconciled|difference
