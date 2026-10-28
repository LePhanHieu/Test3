"""Auth/API integration tests using synthetic users and temporary SQLite only."""

import warnings

import pytest
from sqlalchemy.exc import SAWarning

from skin_cancer.webapp.database_app import create_app
from skin_cancer.webapp.extensions import db, mail
from skin_cancer.webapp.models import AuditLog, DoctorApplication, SecuritySetting, User


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    database_path = tmp_path / "qa-auth.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DERMASCAN_CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setenv("SECRET_KEY", "qa-synthetic-secret-not-for-production")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    for key in ("MAIL_SERVER", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER"):
        monkeypatch.setenv(key, "")

    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "MAIL_SUPPRESS_SEND": True,
            "RATELIMIT_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "REPORT_FOLDER": str(tmp_path / "reports"),
            "MEASUREMENT_FOLDER": str(tmp_path / "measurements"),
        }
    )
    monkeypatch.setattr(mail, "send", lambda *_args, **_kwargs: pytest.fail("Real SMTP must not be used in QA"))

    with app.app_context():
        db.create_all()
        user = User(
            full_name="QA Synthetic User",
            email="synthetic-user@example.invalid",
            role="USER",
            is_active=True,
            email_verified=True,
            two_factor_enabled=False,
        )
        user.set_password("qa-password-1234")
        doctor = User(
            full_name="QA Synthetic Doctor",
            email="synthetic-doctor@example.invalid",
            role="DOCTOR",
            is_active=True,
            email_verified=True,
            two_factor_enabled=False,
        )
        doctor.set_password("qa-password-1234")
        admin = User(
            full_name="QA Synthetic Admin",
            email="synthetic-admin@example.invalid",
            role="ADMIN",
            is_active=True,
            email_verified=True,
            two_factor_enabled=False,
        )
        admin.set_password("qa-password-1234")
        db.session.add_all([user, doctor, admin])
        db.session.flush()
        db.session.add(DoctorApplication(user_id=doctor.id, status="APPROVED"))
        db.session.add(SecuritySetting(id=1, require_admin_2fa=False))
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()

    assert database_path.is_file()


def _csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    assert isinstance(response.json.get("csrf_token"), str)
    return {"X-CSRFToken": response.json["csrf_token"]}


def test_anonymous_user_cannot_read_profile_or_admin_accounts(isolated_app):
    client = isolated_app.test_client()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_login_rejects_missing_csrf_without_creating_audit(isolated_app):
    client = isolated_app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"email": "synthetic-user@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 400
    with isolated_app.app_context():
        assert db.session.query(AuditLog).count() == 0


def test_anonymous_otp_resend_is_rejected_without_sqlalchemy_warning(isolated_app):
    client = isolated_app.test_client()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        response = client.post("/api/auth/resend-2fa", headers=_csrf(client))
    assert response.status_code == 401
    assert not any(issubclass(item.category, SAWarning) for item in caught)


def test_invalid_login_logs_failure_to_temporary_sqlite(isolated_app):
    client = isolated_app.test_client()
    response = client.post(
        "/api/auth/login",
        headers=_csrf(client),
        json={"email": "synthetic-user@example.invalid", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json["success"] is False
    with isolated_app.app_context():
        assert db.session.query(AuditLog).count() == 1


def test_user_login_permissions_and_logout(isolated_app):
    client = isolated_app.test_client()
    response = client.post(
        "/api/auth/login",
        headers=_csrf(client),
        json={"email": "synthetic-user@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 200
    assert response.json["user"]["role"] == "USER"
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_admin_login_reads_accounts_when_qa_two_factor_is_disabled(isolated_app):
    client = isolated_app.test_client()
    response = client.post(
        "/api/auth/admin/login",
        headers=_csrf(client),
        json={"email": "synthetic-admin@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 200
    assert response.json["user"]["role"] == "ADMIN"
    assert client.get("/api/admin/users").status_code == 200


def test_approved_doctor_receives_mock_otp_and_verifies(isolated_app, monkeypatch):
    from skin_cancer.webapp.routes import auth as auth_routes

    isolated_app.config.update(
        MAIL_SERVER="smtp.invalid",
        MAIL_USERNAME="qa-only",
        MAIL_PASSWORD="qa-only",
        MAIL_DEFAULT_SENDER="noreply@example.invalid",
    )
    monkeypatch.setattr(auth_routes.secrets, "randbelow", lambda _limit: 321987)
    sent_messages = []
    monkeypatch.setattr(mail, "send", sent_messages.append)

    client = isolated_app.test_client()
    response = client.post(
        "/api/auth/login",
        headers=_csrf(client),
        json={"email": "synthetic-doctor@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 200
    assert response.json["requires_2fa"] is True
    assert len(sent_messages) == 1
    assert sent_messages[0].recipients == ["synthetic-doctor@example.invalid"]
    assert "321987" in sent_messages[0].body
    assert client.get("/api/auth/me").status_code == 401

    rejected = client.post("/api/auth/verify-2fa", headers=_csrf(client), json={"code": "111111"})
    assert rejected.status_code == 401

    verified = client.post("/api/auth/verify-2fa", headers=_csrf(client), json={"code": "321987"})
    assert verified.status_code == 200, verified.get_json()
    assert verified.json["user"]["role"] == "DOCTOR"
    assert client.get("/api/admin/users").status_code == 403

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        replay = client.post("/api/auth/verify-2fa", headers=_csrf(client), json={"code": "321987"})
    assert replay.status_code == 401
    assert not any(issubclass(item.category, SAWarning) for item in caught)
