"""Batch upload integration checks: all persisted data stays in tmp_path."""

import csv
from io import BytesIO

from PIL import Image
from test_api_auth_isolation import _csrf

from skin_cancer.webapp.extensions import db
from skin_cancer.webapp.models import Case, CaseImage, UploadBatch, User
from skin_cancer.webapp.services.batch_upload import CSV_COLUMNS, BatchUploadService

pytest_plugins = ["test_api_auth_isolation"]


def _png():
    output = BytesIO()
    Image.new("RGB", (32, 32), (23, 125, 190)).save(output, format="PNG")
    return output.getvalue()


def _case(app):
    with app.app_context():
        doctor = db.session.scalar(db.select(User).filter_by(role="DOCTOR"))
        patient = db.session.scalar(db.select(User).filter_by(role="USER"))
        case = Case(case_code="QA-BATCH-001", doctor_id=doctor.id, patient_user_id=patient.id)
        db.session.add(case)
        db.session.commit()
        return case.id


def _login(client, role):
    endpoint = "/api/auth/admin/login" if role == "ADMIN" else "/api/auth/login"
    response = client.post(
        endpoint,
        headers=_csrf(client),
        json={"email": f"synthetic-{role.lower()}@example.invalid", "password": "qa-password-1234"},
    )
    assert response.status_code == 200


def test_anonymous_and_user_cannot_batch_upload(isolated_app):
    case_id = _case(isolated_app)
    client = isolated_app.test_client()
    url = f"/api/cases/{case_id}/upload-batch"

    assert client.post(url, headers=_csrf(client), data={"images": (BytesIO(_png()), "sample.png")}).status_code == 401
    _login(client, "USER")
    assert client.post(url, headers=_csrf(client), data={"images": (BytesIO(_png()), "sample.png")}).status_code == 403

    with isolated_app.app_context():
        assert db.session.query(UploadBatch).count() == 0


def test_admin_batch_handles_valid_invalid_and_duplicate_files_without_aborting(isolated_app):
    case_id = _case(isolated_app)
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    image_bytes = _png()
    response = client.post(
        f"/api/cases/{case_id}/upload-batch",
        headers=_csrf(client),
        data={
            "images": [
                (BytesIO(image_bytes), "valid.png", "image/png"),
                (BytesIO(b"broken"), "invalid.png", "image/png"),
                (BytesIO(image_bytes), "duplicate.png", "image/png"),
            ]
        },
    )

    assert response.status_code == 201, response.get_json()
    result = response.get_json()
    assert result["status"] == "PARTIAL"
    assert (result["total_images"], result["success_count"], result["failed_count"]) == (3, 1, 2)
    assert [item["status"] for item in result["items"]] == ["UPLOADED", "FAILED", "FAILED"]
    assert result["csv_path"] == "private"

    with isolated_app.app_context():
        assert db.session.query(CaseImage).count() == 3
        assert db.session.query(UploadBatch).count() == 1
        batch = db.session.get(UploadBatch, result["batch_id"])
        assert batch.status == "PARTIAL"
        assert batch.csv_path.startswith(isolated_app.config["UPLOAD_FOLDER"])


def test_batch_rejects_empty_submission_without_creating_records(isolated_app):
    case_id = _case(isolated_app)
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    response = client.post(f"/api/cases/{case_id}/upload-batch", headers=_csrf(client), data={})
    assert response.status_code == 400
    with isolated_app.app_context():
        assert db.session.query(UploadBatch).count() == 0


def test_batch_image_limit_rejects_request_before_database_write(isolated_app):
    case_id = _case(isolated_app)
    isolated_app.config["BATCH_MAX_IMAGES"] = 1
    client = isolated_app.test_client()
    _login(client, "ADMIN")
    response = client.post(
        f"/api/cases/{case_id}/upload-batch",
        headers=_csrf(client),
        data={"images": [(BytesIO(_png()), "first.png"), (BytesIO(_png()), "second.png")]},
    )
    assert response.status_code == 400
    with isolated_app.app_context():
        assert db.session.query(UploadBatch).count() == 0
        assert db.session.query(CaseImage).count() == 0


def test_batch_csv_escapes_spreadsheet_formulas_in_temporary_file(tmp_path):
    path = tmp_path / "uploads" / "csv" / "safe.csv"
    row = dict.fromkeys(CSV_COLUMNS, "")
    row.update(filename='=HYPERLINK("https://invalid.example")', error_message="@SUM(1+1)")
    BatchUploadService.write_csv([row], path)

    with path.open(encoding="utf-8", newline="") as handle:
        actual = next(csv.DictReader(handle))
    assert actual["filename"].startswith("'=")
    assert actual["error_message"].startswith("'@")
