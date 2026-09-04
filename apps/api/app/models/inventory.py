"""Inventario: almacenes, lotes, movimientos (fuente de verdad), merma, recepciones y conteos."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDMixin

MOVEMENT_TYPES = ("receipt", "sale", "waste", "count_adjustment", "transfer_out", "transfer_in", "return", "blocked")


class Warehouse(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "warehouses"
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Lot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lots"
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("presentations.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("warehouses.id"))
    produced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|blocked
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class InventoryMovement(UUIDMixin, Base):
    """Cada fila es un delta firmado; el balance = SUM(qty) por (point_id, presentation_id)."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("ix_inv_mov_point_pres", "point_id", "presentation_id"),
        Index("ix_inv_mov_shift", "shift_id"),
    )
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    presentation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("presentations.id"), nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lots.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)  # firmado
    ref_entity: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Waste(UUIDMixin, Base):
    __tablename__ = "waste"
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    presentation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("presentations.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Receipt(UUIDMixin, Base):
    __tablename__ = "receipts"
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    qr_code: Mapped[str | None] = mapped_column(String(160))
    lines: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InventoryCount(UUIDMixin, Base):
    __tablename__ = "inventory_counts"
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual|close|transfer
    counts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    theoretical: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    differences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
