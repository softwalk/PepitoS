"""Casos, alertas, acciones, auditorías, mantenimiento, aprobaciones, IA y reglas."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDMixin


class Case(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_point_status", "point_id", "status"), Index("ix_cases_dedupe", "dedupe_key"))
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # urgent|review|normal
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|in_progress|resolved|closed
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # operator|rule|supervisor|system
    rule_key: Mapped[str | None] = mapped_column(String(40))
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    point_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("points.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    impact_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolution: Mapped[str | None] = mapped_column(Text)
    ai_suggested_category: Mapped[str | None] = mapped_column(String(40))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    point: Mapped["Point | None"] = relationship()  # noqa: F821
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])  # noqa: F821
    actions: Mapped[list["Action"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Alert(UUIDMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_dedupe", "dedupe_key"),)
    rule_key: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|resolved
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    point_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("points.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cases.id"))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Action(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "actions"
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cases.id"))
    audit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("audits.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|done|overdue
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    case: Mapped["Case | None"] = relationship(back_populates="actions")


class Audit(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audits"
    point_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("points.id"), nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"))
    auditor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    checklist: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    cash_counted_cents: Mapped[int | None] = mapped_column(Integer)
    cash_expected_cents: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    non_conformities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaintenanceTicket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_tickets"
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="review", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|in_progress|resolved|closed
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="corrective", nullable=False)  # corrective|preventive
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cases.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    approval_type: Mapped[str] = mapped_column(String(40), nullable=False)  # payment|purchase|cash_difference|other
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|approved|rejected
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AIRecommendation(UUIDMixin, Base):
    __tablename__ = "ai_recommendations"
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    model_version: Mapped[str] = mapped_column(String(60), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    accepted: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Rule(Base):
    __tablename__ = "rules"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="review", nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
