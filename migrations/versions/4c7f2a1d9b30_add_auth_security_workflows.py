"""Add authentication and admin security workflows.

Revision ID: 4c7f2a1d9b30
Revises: 9d731c80a1f2
"""
from alembic import op
import sqlalchemy as sa


revision = "4c7f2a1d9b30"
down_revision = "9d731c80a1f2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_users")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar_url", sa.String(length=500)))
        batch.add_column(sa.Column("deleted_at", sa.DateTime()))
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("email_verification_token_hash", sa.String(length=64)))
        batch.add_column(sa.Column("email_verification_expires_at", sa.DateTime()))
        batch.add_column(sa.Column("password_reset_token_hash", sa.String(length=64)))
        batch.add_column(sa.Column("password_reset_expires_at", sa.DateTime()))
        batch.add_column(sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("two_factor_code_hash", sa.String(length=64)))
        batch.add_column(sa.Column("two_factor_code_expires_at", sa.DateTime()))
        batch.create_unique_constraint("uq_users_email_verification_token_hash", ["email_verification_token_hash"])
        batch.create_unique_constraint("uq_users_password_reset_token_hash", ["password_reset_token_hash"])
    bind.exec_driver_sql("UPDATE users SET email_verified=1 WHERE email_verified=0")

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("event", sa.String(length=80), nullable=False),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=500)),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    bind.exec_driver_sql("PRAGMA foreign_keys=ON")
    op.create_table(
        "security_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("password_min_length", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("require_admin_2fa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "doctor_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("certificate_path", sa.String(length=500)),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    op.drop_table("doctor_applications")
    op.drop_table("security_settings")
    op.drop_table("audit_logs")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_password_reset_token_hash", type_="unique")
        batch.drop_constraint("uq_users_email_verification_token_hash", type_="unique")
        for column in (
            "password_reset_expires_at", "password_reset_token_hash",
            "email_verification_expires_at", "email_verification_token_hash",
            "email_verified", "avatar_url", "deleted_at", "two_factor_code_expires_at",
            "two_factor_code_hash", "two_factor_enabled",
        ):
            batch.drop_column(column)
    bind.exec_driver_sql("PRAGMA foreign_keys=ON")
