"""Report download and email API tests with temporary SQLite, files and SMTP stub."""

from pathlib import Path

from flask_mail import Message
from test_api_auth_isolation import _csrf

from skin_cancer.webapp.extensions import db, mail
from skin_cancer.webapp.models import Analysis, Case, CaseImage, EmailLog, Report, User

pytest_plugins = ["test_api_auth_isolation"]


def _login(client, role):
    endpoint = "/api/auth/admin/login" if role == "ADMIN" else "/api/auth/login"
    response = client.post(
        endpoint,
        headers=_csrf(client),
        json={"email": f"synthetic-{role.lower()}@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 200, response.get_json()


def _report(app, tmp_path, pdf_path="case/report_v1.pdf"):
    with app.app_context():
        user = db.session.scalar(db.select(User).filter_by(role="USER"))
        doctor = db.session.scalar(db.select(User).filter_by(role="DOCTOR"))
        case = Case(case_code="QA-REPORT-001", patient_user_id=user.id, doctor_id=doctor.id)
        db.session.add(case)
        db.session.flush()
        image = CaseImage(
            case_id=case.id,
            image_path="synthetic.png",
            original_filename="synthetic.png",
            mime_type="image/png",
            file_size=5,
            uploaded_by=doctor.id,
            status="UPLOADED",
        )
        db.session.add(image)
        db.session.flush()
        analysis = Analysis(case_id=case.id, case_image_id=image.id, status="COMPLETED")
        db.session.add(analysis)
        db.session.flush()
        report = Report(
            case_id=case.id,
            analysis_id=analysis.id,
            generated_by=doctor.id,
            report_version=1,
            pdf_path=pdf_path,
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    if pdf_path == "case/report_v1.pdf":
        path = Path(tmp_path) / "reports" / pdf_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n% Synthetic QA fixture\n")
    return report_id


def test_anonymous_report_is_private_and_patient_can_download_own_pdf(isolated_app, tmp_path):
    report_id = _report(isolated_app, tmp_path)
    client = isolated_app.test_client()
    assert client.get(f"/api/reports/{report_id}").status_code == 401
    assert client.get(f"/api/reports/{report_id}/download").status_code == 401
    _login(client, "USER")
    response = client.get(f"/api/reports/{report_id}/download")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.data.startswith(b"%PDF-1.4")
    assert client.post(f"/api/reports/{report_id}/email", headers=_csrf(client), json={}).status_code == 403


def test_report_download_rejects_path_traversal(isolated_app, tmp_path):
    report_id = _report(isolated_app, tmp_path, pdf_path="../outside.pdf")
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    assert client.get(f"/api/reports/{report_id}/download").status_code == 404


def test_report_email_rejects_invalid_recipient_without_smtp(isolated_app, tmp_path):
    report_id = _report(isolated_app, tmp_path)
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    response = client.post(
        f"/api/reports/{report_id}/email",
        headers=_csrf(client),
        json={"recipient_email": "bad address"},
    )
    assert response.status_code == 400
    assert response.json["status"] == "FAILED"
    with isolated_app.app_context():
        assert db.session.query(EmailLog).count() == 1


def test_report_email_sends_only_through_mock_and_records_success(isolated_app, tmp_path, monkeypatch):
    report_id = _report(isolated_app, tmp_path)
    isolated_app.config.update(
        MAIL_SERVER="smtp.invalid",
        MAIL_USERNAME="qa-only",
        MAIL_PASSWORD="qa-only",
        MAIL_DEFAULT_SENDER="noreply@example.invalid",
        MAIL_USE_TLS=False,
        MAIL_USE_SSL=False,
    )
    captured = []
    monkeypatch.setattr(mail, "send", captured.append)
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    response = client.post(
        f"/api/reports/{report_id}/email",
        headers=_csrf(client),
        json={"recipient_email": "patient@example.invalid"},
    )
    assert response.status_code == 201, response.get_json()
    assert response.json["status"] == "SENT"
    assert len(captured) == 1
    assert isinstance(captured[0], Message)
    assert captured[0].recipients == ["patient@example.invalid"]
    assert len(captured[0].attachments) == 1
    with isolated_app.app_context():
        assert db.session.query(EmailLog).filter_by(status="SENT").count() == 1


def test_report_email_smtp_error_returns_safe_response_and_logs_failure(isolated_app, tmp_path, monkeypatch):
    report_id = _report(isolated_app, tmp_path)
    isolated_app.config.update(
        MAIL_SERVER="smtp.invalid",
        MAIL_USERNAME="qa-only",
        MAIL_PASSWORD="qa-only",
        MAIL_DEFAULT_SENDER="noreply@example.invalid",
        MAIL_USE_TLS=False,
        MAIL_USE_SSL=False,
    )

    def fake_smtp_failure(_message):
        raise RuntimeError("synthetic SMTP failure: private server detail")

    monkeypatch.setattr(mail, "send", fake_smtp_failure)
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    response = client.post(
        f"/api/reports/{report_id}/email",
        headers=_csrf(client),
        json={"recipient_email": "patient@example.invalid"},
    )
    assert response.status_code == 502
    assert response.json["status"] == "FAILED"
    assert "private server detail" not in response.get_data(as_text=True)
    with isolated_app.app_context():
        log = db.session.scalar(db.select(EmailLog))
        assert log.status == "FAILED"
        assert "synthetic SMTP failure" in log.error_message
