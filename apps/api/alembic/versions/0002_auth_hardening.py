"""Auth hardening: must_change_password, login_attempts, refresh_tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'login_attempts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('ip', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_login_attempts_username_at', 'login_attempts', ['username', 'at'], unique=False)
    op.create_index('ix_login_attempts_ip_at', 'login_attempts', ['ip', 'at'], unique=False)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sa.String(length=120), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_refresh_tokens_user', 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_device', 'refresh_tokens', ['device_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_device', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_login_attempts_ip_at', table_name='login_attempts')
    op.drop_index('ix_login_attempts_username_at', table_name='login_attempts')
    op.drop_table('login_attempts')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'must_change_password')
