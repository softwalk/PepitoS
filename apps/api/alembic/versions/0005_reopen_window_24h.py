"""Ventana de reapertura de turno: 12 h → 24 h (la regla "mismo día" ya acota; 12 h bloqueaba cierres de la mañana por la tarde)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sólo si sigue con el valor por defecto anterior (no pisar un valor editado por el administrador).
    op.get_bind().execute(sa.text("UPDATE settings SET value = '24'::jsonb, updated_at = now() WHERE key = 'shift_reopen_window_hours' AND value = '12'::jsonb"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE settings SET value = '12'::jsonb WHERE key = 'shift_reopen_window_hours' AND value = '24'::jsonb"))
