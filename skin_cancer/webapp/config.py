"""
Application/database configuration.

Các đường dẫn độc lập với working directory.
Thông tin nhạy cảm được đọc từ .env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

INSTANCE_DIR = (
    PROJECT_ROOT
    / "instance"
)


def _env_bool(
    name,
    default=False,
):

    value = os.getenv(
        name,
        str(default),
    )

    return (
        str(value)
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def database_config():

    # Không ghi password trực tiếp vào source.
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
    )

    mail_port = int(
        os.getenv(
            "MAIL_PORT",
            "587",
        )
    )

    mail_use_tls = _env_bool(
        "MAIL_USE_TLS",
        True,
    )

    mail_use_ssl = _env_bool(
        "MAIL_USE_SSL",
        False,
    )

    # TLS và SSL không được bật cùng lúc.
    if (
        mail_use_tls
        and mail_use_ssl
    ):
        raise RuntimeError(
            "MAIL_USE_TLS và MAIL_USE_SSL "
            "không được cùng bằng true."
        )

    return {

        # ====================================================
        # CORE
        # ====================================================

        "SECRET_KEY":
            os.getenv(
                "SECRET_KEY"
            ),

        "PROJECT_ROOT":
            str(PROJECT_ROOT),

        # ====================================================
        # DATABASE
        # ====================================================

        "SQLALCHEMY_DATABASE_URI":
            os.getenv(
                "DATABASE_URL",
                "sqlite:///"
                + (
                    INSTANCE_DIR
                    / "dermascan_live.db"
                ).as_posix(),
            ),

        "SQLALCHEMY_TRACK_MODIFICATIONS":
            False,

        # ====================================================
        # STORAGE
        # ====================================================

        "REPORT_FOLDER":
            str(
                INSTANCE_DIR
                / "reports"
            ),

        "UPLOAD_FOLDER":
            str(
                INSTANCE_DIR
                / "uploads"
            ),

        "MEASUREMENT_FOLDER":
            str(
                INSTANCE_DIR
                / "measurements"
            ),

        "REPORT_LOGO_PATH":
            str(
                Path(__file__)
                .resolve()
                .parent
                / "assets"
                / "dermascan_logo.png"
            ),

        # ====================================================
        # UPLOAD
        # ====================================================

        "BATCH_MAX_IMAGES":
            20,

        "BATCH_MAX_FILE_BYTES":
            10 * 1024 * 1024,

        "BATCH_MAX_IMAGE_PIXELS":
            25_000_000,

        "MAX_CONTENT_LENGTH":
            (
                20 * 10 * 1024 * 1024
                + 1024 * 1024
            ),

        # ====================================================
        # SESSION
        # ====================================================

        "SESSION_COOKIE_HTTPONLY":
            True,

        "SESSION_COOKIE_SAMESITE":
            "Lax",

        "SESSION_COOKIE_SECURE":
            _env_bool(
                "SESSION_COOKIE_SECURE",
                False,
            ),

        # JavaScript clients obtain a same-session token from /api/auth/csrf
        # and send it on unsafe requests.  Keep both conventional Flask-WTF
        # spellings available while the UI is being served from cached assets.
        "WTF_CSRF_HEADERS": (
            "X-CSRFToken",
            "X-CSRF-Token",
        ),

        # ====================================================
        # RATE LIMITING
        # ====================================================

        "RATELIMIT_ENABLED":
            _env_bool(
                "RATELIMIT_ENABLED",
                True,
            ),

        "RATELIMIT_STORAGE_URI":
            os.getenv(
                "RATELIMIT_STORAGE_URI",
                "memory://",
            ).strip(),

        "RATELIMIT_LOGIN":
            os.getenv(
                "RATELIMIT_LOGIN",
                "5 per minute",
            ).strip(),

        "RATELIMIT_EXPENSIVE":
            os.getenv(
                "RATELIMIT_EXPENSIVE",
                "30 per hour",
            ).strip(),

        "RATELIMIT_REPORT":
            os.getenv(
                "RATELIMIT_REPORT",
                "20 per hour",
            ).strip(),

        # ====================================================
        # DEMO
        # ====================================================

        "ALLOW_DEMO_SEED":
            _env_bool(
                "ALLOW_DEMO_SEED",
                False,
            ),

        # ====================================================
        # EMAIL / SMTP
        # ====================================================

        "MAIL_SERVER":
            os.getenv(
                "MAIL_SERVER",
                "",
            ).strip(),

        "MAIL_PORT":
            mail_port,

        "MAIL_USE_TLS":
            mail_use_tls,

        "MAIL_USE_SSL":
            mail_use_ssl,

        "MAIL_USERNAME":
            os.getenv(
                "MAIL_USERNAME",
                "",
            ).strip(),

        "MAIL_PASSWORD":
            os.getenv(
                "MAIL_PASSWORD",
                "",
            ),

        "MAIL_DEFAULT_SENDER":
            os.getenv(
                "MAIL_DEFAULT_SENDER",
                "",
            ).strip(),

        "MAIL_TIMEOUT":
            float(
                os.getenv(
                    "MAIL_TIMEOUT",
                    "30",
                )
            ),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
    }