"""Movimientos de caja, costos por punto, MFA TOTP, suscripciones push y bitácora de notificaciones

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cash_movements',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('shift_id', sa.Uuid(), sa.ForeignKey('shifts.id'), nullable=False),
        sa.Column('point_id', sa.Uuid(), sa.ForeignKey('points.id'), nullable=False),
        sa.Column('actor_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(160), nullable=False),
        sa.Column('note', sa.Text()),
        sa.Column('idempotency_key', sa.String(120), unique=True, nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('case_id', sa.Uuid(), sa.ForeignKey('cases.id')),
    )
    op.create_index('ix_cash_movements_shift', 'cash_movements', ['shift_id', 'occurred_at'])
    op.create_table(
        'point_costs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('point_id', sa.Uuid(), sa.ForeignKey('points.id'), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('rent_month_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('permit_month_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('custody_month_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('other_month_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('setup_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('note', sa.Text()),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id')),
    )
    op.create_index('ix_point_costs_point_valid', 'point_costs', ['point_id', 'valid_from'])
    op.add_column('users', sa.Column('totp_secret', sa.String(64)))
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('mfa_enabled_at', sa.DateTime(timezone=True)))
    op.add_column('users', sa.Column('notify_prefs', postgresql.JSONB(), nullable=False, server_default='{}'))
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('endpoint', sa.Text(), unique=True, nullable=False),
        sa.Column('p256dh', sa.Text(), nullable=False),
        sa.Column('auth', sa.Text(), nullable=False),
        sa.Column('user_agent', sa.String(200)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error', sa.Text()),
        sa.Column('disabled_at', sa.DateTime(timezone=True)),
    )
    op.create_table(
        'notification_log',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id')),
        sa.Column('dedupe_key', sa.String(200)),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error', sa.Text()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_notification_log_key', 'notification_log', ['dedupe_key'])


def downgrade() -> None:
    op.drop_table('notification_log')
    op.drop_table('push_subscriptions')
    for col in ('totp_secret', 'mfa_enabled', 'mfa_enabled_at', 'notify_prefs'):
        op.drop_column('users', col)
    op.drop_table('point_costs')
    op.drop_table('cash_movements')
