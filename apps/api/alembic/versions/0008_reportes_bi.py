"""Índices para el módulo de Reportes (BI)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-04
"""
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_sales_occurred_point", "sales", ["occurred_at", "point_id"]),
    ("ix_sales_operator_occurred", "sales", ["operator_id", "occurred_at"]),
    ("ix_sale_lines_presentation", "sale_lines", ["presentation_id", "sale_id"]),
    ("ix_payments_method_occurred", "payments", ["method", "occurred_at"]),
    ("ix_inventory_movements_point_occurred", "inventory_movements", ["point_id", "occurred_at"]),
    ("ix_waste_occurred_point", "waste", ["occurred_at", "point_id"]),
    ("ix_cases_point_opened", "cases", ["point_id", "opened_at"]),
    ("ix_shifts_opened_point", "shifts", ["opened_at", "point_id"]),
    ("ix_gps_pings_at_shift", "gps_pings", ["at", "shift_id"]),
    ("ix_audits_performed_point", "audits", ["performed_at", "point_id"]),
    ("ix_assignments_shift_date_point", "assignments", ["shift_date", "point_id"]),
    ("ix_audit_log_action_at", "audit_log", ["action", "at"]),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.create_index(name, table, cols, if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
