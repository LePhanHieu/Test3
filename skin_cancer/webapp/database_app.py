"""
Database/application bootstrap.

Dùng cho:
python -m flask --app skin_cancer.webapp.database_app db upgrade
"""

from datetime import timedelta
from flask import Flask, session

from .config import (
    INSTANCE_DIR,
    PROJECT_ROOT,
    database_config,
)

from .extensions import (
    db,
    migrate,
    mail,
)


def init_database(app, config=None):

    # --------------------------------------------------------
    # LOAD CONFIG
    # --------------------------------------------------------

    app.config.update(
        database_config()
    )

    if config:
        app.config.update(config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "Thiếu SECRET_KEY: đặt biến môi trường "
            "hoặc .env trước khi chạy"
        )

    INSTANCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    db.init_app(app)

    from . import models  # noqa: F401

    migrate.init_app(
        app,
        db,
        directory=str(
            PROJECT_ROOT / "migrations"
        ),
        render_as_batch=True,
        compare_type=True,
    )

    # --------------------------------------------------------
    # FLASK-MAIL
    #
    # PHẦN NÀY TRƯỚC ĐÓ BỊ THIẾU
    # --------------------------------------------------------

    mail.init_app(app)

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    from .bootstrap import (
        register_database_api,
    )
    register_database_api(app)

    @app.before_request
    def enforce_configured_session_timeout():
        setting = db.session.get(models.SecuritySetting, 1)
        minutes = setting.session_timeout_minutes if setting else 30
        app.permanent_session_lifetime = timedelta(minutes=minutes)
        if session.get("_user_id"):
            session.permanent = True
            session.modified = True

    # --------------------------------------------------------
    # SEED
    # --------------------------------------------------------

    from .initial_setup import register_initial_setup
    register_initial_setup(app)


def create_app(config=None):
    app = Flask(
        __name__,
        instance_path=str(
            INSTANCE_DIR
        ),
    )

    init_database(
        app,
        config,
    )

    return app