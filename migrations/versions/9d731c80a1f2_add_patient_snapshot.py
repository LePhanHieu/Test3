"""Add temporary patient snapshot to cases.

Revision ID: 9d731c80a1f2
Revises: e8e27e26f978
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION
# ============================================================

revision = "9d731c80a1f2"

down_revision = "e8e27e26f978"

branch_labels = None

depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    connection = op.get_bind()

    # --------------------------------------------------------
    # SQLite:
    #
    # Alembic batch mode phải tạo bảng tạm rồi DROP cases.
    # Nhưng nhiều bảng khác đang có FK -> cases.
    #
    # Vì vậy tạm tắt FK trong thời gian rebuild.
    # --------------------------------------------------------

    connection.exec_driver_sql(
        "PRAGMA foreign_keys=OFF"
    )


    foreign_keys_enabled = (
        connection
        .exec_driver_sql(
            "PRAGMA foreign_keys"
        )
        .scalar()
    )


    if foreign_keys_enabled != 0:

        raise RuntimeError(
            "Không thể tắt SQLite foreign_keys. "
            "Hãy dừng Flask và chạy migration lại."
        )


    try:

        # ----------------------------------------------------
        # Nếu lần migration trước đã lỗi ở DROP TABLE cases,
        # Alembic có thể để lại bảng tạm.
        #
        # Chỉ xóa bảng tạm, KHÔNG xóa bảng cases thật.
        # ----------------------------------------------------

        connection.exec_driver_sql(
            """
            DROP TABLE IF EXISTS
            _alembic_tmp_cases
            """
        )


        # ----------------------------------------------------
        # REBUILD CASES
        # ----------------------------------------------------

        with op.batch_alter_table(
            "cases",
            schema=None,
            recreate="always",
        ) as batch_op:

            # ================================================
            # PATIENT SNAPSHOT
            # ================================================

            batch_op.add_column(
                sa.Column(
                    "patient_snapshot",
                    sa.JSON(),
                    nullable=True,
                )
            )


            # ================================================
            # PATIENT USER
            #
            # NULL = bệnh nhân tạm.
            # Có ID = bệnh nhân có tài khoản USER.
            # ================================================

            batch_op.alter_column(
                "patient_user_id",

                existing_type=
                    sa.Integer(),

                nullable=True,
            )


            # ================================================
            # PATIENT SOURCE CHECK
            # ================================================

            batch_op.create_check_constraint(
                "patient_source",

                (
                    "patient_user_id IS NOT NULL "
                    "OR patient_snapshot IS NOT NULL"
                ),
            )


    finally:

        # ----------------------------------------------------
        # Bật lại Foreign Key.
        # ----------------------------------------------------

        connection.exec_driver_sql(
            "PRAGMA foreign_keys=ON"
        )


    # --------------------------------------------------------
    # Kiểm tra FK sau khi rebuild.
    # --------------------------------------------------------

    violations = (
        connection
        .exec_driver_sql(
            "PRAGMA foreign_key_check"
        )
        .fetchall()
    )


    if violations:

        raise RuntimeError(
            "Foreign key check thất bại "
            f"sau migration: {violations}"
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    connection = op.get_bind()


    # --------------------------------------------------------
    # Không thể quay về NOT NULL nếu đã tồn tại bệnh nhân tạm.
    # --------------------------------------------------------

    temporary_count = (
        connection
        .exec_driver_sql(
            """
            SELECT COUNT(*)
            FROM cases
            WHERE patient_user_id IS NULL
            """
        )
        .scalar()
    )


    if temporary_count:

        raise RuntimeError(
            "Không thể downgrade vì database "
            "đang có Case của bệnh nhân tạm."
        )


    # --------------------------------------------------------
    # SQLite FK OFF cho batch rebuild.
    # --------------------------------------------------------

    connection.exec_driver_sql(
        "PRAGMA foreign_keys=OFF"
    )


    foreign_keys_enabled = (
        connection
        .exec_driver_sql(
            "PRAGMA foreign_keys"
        )
        .scalar()
    )


    if foreign_keys_enabled != 0:

        raise RuntimeError(
            "Không thể tắt SQLite foreign_keys."
        )


    try:

        connection.exec_driver_sql(
            """
            DROP TABLE IF EXISTS
            _alembic_tmp_cases
            """
        )


        with op.batch_alter_table(
            "cases",
            schema=None,
            recreate="always",
        ) as batch_op:

            batch_op.drop_constraint(
                "patient_source",
                type_="check",
            )


            batch_op.alter_column(
                "patient_user_id",

                existing_type=
                    sa.Integer(),

                nullable=False,
            )


            batch_op.drop_column(
                "patient_snapshot",
            )


    finally:

        connection.exec_driver_sql(
            "PRAGMA foreign_keys=ON"
        )


    violations = (
        connection
        .exec_driver_sql(
            "PRAGMA foreign_key_check"
        )
        .fetchall()
    )


    if violations:

        raise RuntimeError(
            "Foreign key check thất bại "
            f"sau downgrade: {violations}"
        )