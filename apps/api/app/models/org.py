"""Zonas, usuarios, dispositivos, puntos, carritos, activos, asignaciones, asistencia."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
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
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Ranking de ventas del vendedor (1 = mejor) por día, mes y año locales; lo recalcula el motor cada corrida y cada cierre.
    sales_rank_day: Mapped[int | None] = mapped_column(Integer)
    sales_rank_month: Mapped[int | None] = mapped_column(Integer)
    sales_rank_year: Mapped[int | None] = mapped_column(Integer)
    sales_day_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sales_month_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sales_year_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sales_rank_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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


class RefreshToken(Base):
    """Refresh token opaco y rotativo (B3). Se guarda sólo el SHA-256; `replaced_by` encadena la rotación."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user", "user_id"), Index("ix_refresh_tokens_device", "device_id"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class LoginAttempt(Base):
    """Intentos de login (B2) para rate limiting por usuario e IP."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_username_at", "username", "at"), Index("ix_login_attempts_ip_at", "ip", "at"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)


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
    # Coordenadas confirmadas en campo. Mientras sea False la apertura usa `geofence_radius_m` como tolerancia en vez de
    # la regla estricta `open_max_distance_m` (50 m), porque una coordenada aproximada generaría falsos "fuera de punto".
    geo_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Ficha del punto autorizado (ranking, alcaldía, tipo de nodo, score, horario sugerido, justificación, fuente…).
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    zone: Mapped["Zone | None"] = relationship()

    @property
    def score(self) -> int | None:
        """Score estratégico (/100) del catálogo de ubicaciones, si el punto proviene de él."""
        v = (self.meta or {}).get("score")
        try:
            return int(round(float(v))) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def display_name(self) -> str:
        """Nombre que se muestra en todo el sistema: «Nombre - Score» cuando hay score estratégico."""
        return f"{self.name} - {self.score}" if self.score is not None else self.name


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
