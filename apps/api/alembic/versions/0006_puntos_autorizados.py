"""Puntos autorizados: geo_verified + meta en points; parámetro open_max_distance_m (50 m)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-04
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los puntos existentes se dieron de alta a mano con coordenadas conocidas: se consideran verificados.
    op.add_column('points', sa.Column('geo_verified', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('points', sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'))
    op.get_bind().execute(
        sa.text("INSERT INTO settings (key, value, updated_at) VALUES (:k, CAST(:v AS jsonb), now()) ON CONFLICT (key) DO NOTHING"),
        {"k": "open_max_distance_m", "v": json.dumps(50)},
    )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'open_max_distance_m'")
    op.drop_column('points', 'meta')
    op.drop_column('points', 'geo_verified')
