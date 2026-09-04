"""Importa todos los modelos para que Base.metadata esté completo (Alembic)."""
from app.models.org import Assignment, Asset, Attendance, Cart, Device, Point, RevokedToken, User, Zone  # noqa: F401
from app.models.ops import CashSession, Checklist, ChecklistResult, GpsPing, Shift  # noqa: F401
from app.models.catalog import DailyTarget, Flavor, Presentation, PriceItem, PriceVersion, Product  # noqa: F401
from app.models.sales import Payment, Sale, SaleCancellation, SaleLine  # noqa: F401
from app.models.inventory import InventoryCount, InventoryMovement, Lot, Receipt, Warehouse, Waste  # noqa: F401
from app.models.cases import (  # noqa: F401
    Action,
    AIRecommendation,
    Alert,
    Approval,
    Audit,
    Case,
    MaintenanceTicket,
    Rule,
)
from app.models.system import AuditLog, Event, IdempotencyKey  # noqa: F401
