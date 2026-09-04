"""Productos, presentaciones, sabores, precios versionados y metas diarias."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDMixin


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "products"
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Presentation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "presentations"
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    grams: Mapped[int] = mapped_column(Integer, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Flavor(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "flavors"
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PriceVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "price_versions"
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    items: Mapped[list["PriceItem"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class PriceItem(UUIDMixin, Base):
    __tablename__ = "price_items"
    __table_args__ = (UniqueConstraint("price_version_id", "presentation_id", name="uq_price_item"),)
    price_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("price_versions.id"), nullable=False)
    presentation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("presentations.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    version: Mapped["PriceVersion"] = relationship(back_populates="items")


class DailyTarget(UUIDMixin, Base):
    __tablename__ = "daily_targets"
    __table_args__ = (UniqueConstraint("point_id", "target_date", name="uq_daily_target"),)
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    target_tx: Mapped[int] = mapped_column(Integer, nullable=False)
