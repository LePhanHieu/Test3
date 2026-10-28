"""Lưu lý do từ chối hồ sơ bác sĩ.

Revision ID: 7b2d19a80c13
Revises: c6d91a2b4037
"""
from alembic import op
import sqlalchemy as sa


revision = "7b2d19a80c13"
down_revision = "c6d91a2b4037"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("doctor_applications") as batch:
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("email_notification_status", sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table("doctor_applications") as batch:
        batch.drop_column("rejection_reason")
        batch.drop_column("email_notification_status")