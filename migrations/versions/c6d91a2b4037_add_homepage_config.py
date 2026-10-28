"""Bổ sung cấu hình nội dung trang chủ mà không tạo bảng mới.

Revision ID: c6d91a2b4037
Revises: 4c7f2a1d9b30
"""
from alembic import op
import sqlalchemy as sa


revision = "c6d91a2b4037"
down_revision = "4c7f2a1d9b30"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("site_settings") as batch:
        batch.add_column(sa.Column("homepage_config", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("homepage_config")