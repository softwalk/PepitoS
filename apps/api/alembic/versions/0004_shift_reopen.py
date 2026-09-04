"""Continuar turno (admin): índice para último turno por asignación y parámetro shift_reopen_window_hours

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-04
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_shifts_assignment_opened", "shifts", ["assignment_id", "opened_at"], unique=False)
    op.get_bind().execute(
        sa.text("INSERT INTO settings (key, value, updated_at) VALUES (:k, CAST(:v AS jsonb), now()) ON CONFLICT (key) DO NOTHING"),
        {"k": "shift_reopen_window_hours", "v": json.dumps(12)},
    )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'shift_reopen_window_hours'")
    op.drop_index("ix_shifts_assignment_opened", table_name="shifts")
