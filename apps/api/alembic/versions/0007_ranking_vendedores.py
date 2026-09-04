"""Ranking de ventas por vendedor (día/mes/año) guardado en users

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in ("sales_rank_day", "sales_rank_month", "sales_rank_year"):
        op.add_column('users', sa.Column(col, sa.Integer(), nullable=True))
    for col in ("sales_day_cents", "sales_month_cents", "sales_year_cents"):
        op.add_column('users', sa.Column(col, sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('sales_rank_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("sales_rank_day", "sales_rank_month", "sales_rank_year", "sales_day_cents", "sales_month_cents", "sales_year_cents", "sales_rank_at"):
        op.drop_column('users', col)
