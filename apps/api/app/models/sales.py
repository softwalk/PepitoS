"""Ledger de ventas (append-only): sales, sale_lines, payments, sale_cancellations."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDMixin


class Sale(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (Index("ix_sales_shift", "shift_id"), Index("ix_sales_point_occurred", "point_id", "occurred_at"))
    folio_num: Mapped[int] = mapped_column(Integer, Identity(start=1), unique=True, nullable=False)
    folio: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    cart_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("carts.id"))
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(120))
    price_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("price_versions.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="recorded", nullable=False)  # recorded|cancelled
    offline_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gps: Mapped[dict | None] = mapped_column(JSONB)

    lines: Mapped[list["SaleLine"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    cancellation: Mapped["SaleCancellation | None"] = relationship(back_populates="sale", uselist=False)


class SaleLine(UUIDMixin, Base):
    __tablename__ = "sale_lines"
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sales.id"), nullable=False)
    presentation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("presentations.id"), nullable=False)
    flavor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("flavors.id"))
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="lines")


class Payment(UUIDMixin, Base):
    __tablename__ = "payments"
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sales.id"), nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # cash|qr|card
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))

    sale: Mapped["Sale"] = relationship(back_populates="payments")


class SaleCancellation(UUIDMixin, Base):
    __tablename__ = "sale_cancellations"
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sales.id"), unique=True, nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="cancellation")
