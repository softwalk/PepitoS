"""Zonas, usuarios, dispositivos, puntos, carritos, activos, asignaciones, asistencia."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDMixin


class Zone(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "zones"
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # operator|supervisor|ops|finance|admin
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("zones.id"), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    zone: Mapped["Zone | None"] = relationship()


class Device(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    device_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)  # UUID generado por el cliente
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str | None] = mapped_column(String(160))
    platform: Mapped[str | None] = mapped_column(String(60))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Point(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "points"
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("zones.id"))
    open_time: Mapped[str | None] = mapped_column(String(5))  # "08:00" hora local
    close_time: Mapped[str | None] = mapped_column(String(5))
    daily_target_cents: Mapped[int] = mapped_column(Integer, default=234000, nullable=False)
    daily_target_tx: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    zone: Mapped["Zone | None"] = relationship()


class Cart(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "carts"
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)  # cart|battery|charger|pos|other
    cart_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("carts.id"))
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    maintenance_interval_days: Mapped[int | None] = mapped_column(Integer)
    last_maintenance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_maintenance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Assignment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("operator_id", "shift_date", name="uq_assignment_operator_date"),)
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    cart_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("carts.id"), nullable=False)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)  # planned|started|done|absent

    operator: Mapped["User"] = relationship()
    point: Mapped["Point"] = relationship()
    cart: Mapped["Cart"] = relationship()


class Attendance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attendance"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assignments.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="present", nullable=False)  # present|late|absent
