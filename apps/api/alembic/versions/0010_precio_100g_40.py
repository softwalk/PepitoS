"""Actualización precio presentación 100g a $40 MXN (4000 centavos)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09
"""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Actualiza el precio de la presentación de 100 g a 4000 centavos ($40 MXN)
    op.execute("""
        UPDATE price_items
        SET amount_cents = 4000
        WHERE presentation_id IN (
            SELECT id FROM presentations WHERE grams = 100
        )
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE price_items
        SET amount_cents = 4500
        WHERE presentation_id IN (
            SELECT id FROM presentations WHERE grams = 100
        )
    """)
