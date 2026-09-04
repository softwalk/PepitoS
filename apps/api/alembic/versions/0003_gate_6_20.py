"""Gate 6-20: evidencias en object storage (B4), settings editables (B6), ventana de precio offline (B8)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

# Claves iniciales de `settings` (mismas en demo y prod). El seed también las garantiza (idempotente).
INITIAL_SETTINGS = {
    "cash_difference_threshold_cents": 2000,
    "cash_difference_severe_cents": 10000,
    "cancel_window_minutes": 5,
    "gps_interval_seconds": 120,
    "photo_sampling_pct": 10,
    "evidence_retention_days": 180,
    "gps_retention_days": 90,
    "daily_sales_target_default_cents": 234000,
    "inventory_count_tolerance_units": 3,
}

# Parámetros de reglas que ahora viven en settings: si en `rules.params` siguen con el valor por defecto
# se eliminan para que aplique la precedencia rules.params > settings > default.
RULE_PARAMS_MOVED = {
    "cash_difference": {"threshold_cents": 2000, "severe_cents": 10000},
    "inventory_inconsistent": {"units": 3},
}


def upgrade() -> None:
    # ---- B4: evidence ----
    op.create_table(
        'evidence',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('entity', sa.String(length=40), nullable=False),
        sa.Column('entity_id', sa.Uuid(), nullable=False),
        sa.Column('point_id', sa.Uuid(), nullable=True),
        sa.Column('shift_id', sa.Uuid(), nullable=True),
        sa.Column('uploaded_by', sa.Uuid(), nullable=True),
        sa.Column('storage_key', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=60), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('taken_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['point_id'], ['points.id']),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_entity', 'evidence', ['entity', 'entity_id'], unique=False)
    op.create_index('ix_evidence_point', 'evidence', ['point_id'], unique=False)

    # ---- B6: settings ----
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('key'),
    )
    conn = op.get_bind()
    for key, value in INITIAL_SETTINGS.items():
        conn.execute(
            sa.text("INSERT INTO settings (key, value, updated_at) VALUES (:k, CAST(:v AS jsonb), now()) ON CONFLICT (key) DO NOTHING"),
            {"k": key, "v": json.dumps(value)},
        )
    for rule_key, moved in RULE_PARAMS_MOVED.items():
        row = conn.execute(sa.text("SELECT params FROM rules WHERE key = :k"), {"k": rule_key}).first()
        if row is None:
            continue
        params = dict(row[0] or {})
        changed = False
        for pk, default in moved.items():
            if pk in params and params[pk] == default:
                params.pop(pk)
                changed = True
        if changed:
            conn.execute(sa.text("UPDATE rules SET params = CAST(:p AS jsonb) WHERE key = :k"), {"p": json.dumps(params), "k": rule_key})

    # ---- B8: ventana de precio tolerante ----
    op.add_column('price_versions', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE price_versions SET deactivated_at = updated_at WHERE is_active = false AND deactivated_at IS NULL")
    op.add_column('sales', sa.Column('price_version_stale', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('sales', 'price_version_stale')
    op.drop_column('price_versions', 'deactivated_at')
    op.drop_table('settings')
    op.drop_index('ix_evidence_point', table_name='evidence')
    op.drop_index('ix_evidence_entity', table_name='evidence')
    op.drop_table('evidence')
