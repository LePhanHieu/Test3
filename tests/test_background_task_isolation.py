"""Worker state transitions with a fake inference function and temporary SQLite."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from skin_cancer.webapp import tasks
from skin_cancer.webapp.extensions import db
from skin_cancer.webapp.models import Analysis, AnalysisResult, Case, CaseImage, User

pytest_plugins = ["test_api_auth_isolation"]


def _setup_analysis(app, image_path):
    with app.app_context():
        doctor = db.session.scalar(db.select(User).filter_by(role="DOCTOR"))
        patient = db.session.scalar(db.select(User).filter_by(role="USER"))
        case = Case(case_code="QA-WORKER-001", doctor_id=doctor.id, patient_user_id=patient.id)
        db.session.add(case)
        db.session.flush()
        case_image = CaseImage(
            case_id=case.id,
            image_path=str(image_path),
            original_filename="synthetic.png",
            mime_type="image/png",
            file_size=10,
            uploaded_by=doctor.id,
            status="UPLOADED",
        )
        db.session.add(case_image)
        db.session.flush()
        analysis = Analysis(case_id=case.id, case_image_id=case_image.id, status="PENDING")
        db.session.add(analysis)
        db.session.commit()
        return analysis.id, case_image.id, case.id


def _fake_webapp(app, root, inference=None):
    return SimpleNamespace(
        app=app,
        PROJECT_ROOT=Path(root),
        utcnow_naive=lambda: datetime.now(UTC).replace(tzinfo=None),
        run_ai_inference=inference,
    )


def test_local_worker_marks_invalid_image_failed_and_restores_upload_status(isolated_app, tmp_path, monkeypatch):
    analysis_id, case_image_id, _ = _setup_analysis(isolated_app, tmp_path / "missing.png")
    monkeypatch.setattr(tasks, "_webapp", lambda: _fake_webapp(isolated_app, tmp_path))
    assert tasks._run_analysis(analysis_id, case_image_id) is None

    with isolated_app.app_context():
        analysis = db.session.get(Analysis, analysis_id)
        assert analysis.status == "FAILED"
        assert "File ảnh không hợp lệ" in analysis.error_message
        assert db.session.get(CaseImage, case_image_id).status == "UPLOADED"
        assert db.session.query(AnalysisResult).count() == 0


def test_local_worker_writes_fake_inference_result_and_gradcam_only_under_tmp(isolated_app, tmp_path, monkeypatch):
    image_path = tmp_path / "synthetic.png"
    Image.new("RGB", (256, 256), (120, 80, 60)).save(image_path)
    analysis_id, case_image_id, case_id = _setup_analysis(isolated_app, image_path)
    cached = []
    monkeypatch.setattr(tasks, "save_cached", lambda key, value: cached.append((key, value)))

    def fake_inference(_image, context=None):
        result = {
            "binary": {"prediction": 0, "prob_malignant": 0.12},
            "multiclass": {"pred_class": "NV", "pred_conf": 0.88, "probs": {"NV": 0.88, "MEL": 0.12}},
        }
        return result, np.full((224, 224, 3), 100, dtype=np.uint8), 15.0

    monkeypatch.setattr(tasks, "_webapp", lambda: _fake_webapp(isolated_app, tmp_path, fake_inference))
    result = tasks._run_analysis(analysis_id, case_image_id)
    assert result is not None
    assert result["analysis_id"] == analysis_id
    assert len(cached) == 1
    assert cached[0][0] == f"analysis-result:{analysis_id}"

    with isolated_app.app_context():
        analysis = db.session.get(Analysis, analysis_id)
        assert analysis.status == "COMPLETED"
        assert db.session.get(CaseImage, case_image_id).status == "COMPLETED"
        assert db.session.get(Case, case_id).status == "ANALYZED"
        assert db.session.query(AnalysisResult).count() == 1
        assert Path(analysis.gradcam_path).is_relative_to(tmp_path / "instance" / "gradcam")
        assert Path(analysis.gradcam_path).is_file()
