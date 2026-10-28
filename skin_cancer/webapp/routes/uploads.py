from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    request,
    send_file,
)
from flask_login import current_user

from ..extensions import db, limiter
from ..models import UploadBatch
from ..services.access import (
    require_roles,
    visible_case_or_404,
)
from ..services.analysis_csv import AnalysisCsvService
from ..services.analysis_excel import AnalysisExcelService
from ..services.batch_upload import (
    BatchUploadService,
)

bp = Blueprint(
    "uploads",
    __name__,
    url_prefix="/api",
)


@bp.post(
    "/cases/<int:case_id>/upload-batch"
)
@limiter.limit(
    lambda: current_app.config["RATELIMIT_EXPENSIVE"]
)
@require_roles("ADMIN", "DOCTOR")
def upload_batch(case_id):

    case = visible_case_or_404(
        case_id
    )

    files = request.files.getlist(
        "images"
    )

    if not files:
        abort(
            400,
            description=(
                "Cần gửi ít nhất một file "
                "trong field images"
            ),
        )

    max_images = int(
        current_app.config[
            "BATCH_MAX_IMAGES"
        ]
    )

    if len(files) > max_images:
        abort(
            400,
            description=(
                "Batch vượt giới hạn tối đa "
                f"{max_images} ảnh"
            ),
        )

    batch = UploadBatch(
        case_id=case.id,
        doctor_id=current_user.id,
        total_images=len(files),
        status="PROCESSING",
    )

    db.session.add(batch)
    db.session.flush()

    service = BatchUploadService(
        current_app,
        batch,
        case,
        current_user,
    )

    result = None
    csv_path = None
    created_files = []

    try:

        result = service.process(files)

        created_files = [
            service.upload_root
            / "images"
            / item["filename"]
            for item in result.items
            if (
                item["status"] == "UPLOADED"
                and item["filename"]
            )
        ]

        batch.success_count = (
            result.success_count
        )

        batch.failed_count = (
            result.failed_count
        )

        if result.failed_count == 0:

            batch.status = "COMPLETED"

        elif result.success_count == 0:

            batch.status = "FAILED"

        else:

            batch.status = "PARTIAL"

        batch.completed_at = (
            datetime.now(timezone.utc)
        )

        if (
            batch.success_count > 0
            and case.status == "CREATED"
        ):
            case.status = "UPLOADED"

        csv_path = (
            service.upload_root
            / "csv"
            / f"batch_{batch.id}.csv"
        )

        BatchUploadService.write_csv(
            result.rows,
            csv_path,
        )

        batch.csv_path = str(
            csv_path.resolve()
        )

        batch.item_results = (
            result.items
        )

        db.session.commit()

    except Exception:

        db.session.rollback()

        for created_file in created_files:
            created_file.unlink(
                missing_ok=True
            )

        if csv_path:
            csv_path.unlink(
                missing_ok=True
            )

        raise

    return jsonify(
        batch_id=batch.id,
        case_id=case.id,
        case_code=case.case_code,
        total_images=batch.total_images,
        success_count=batch.success_count,
        failed_count=batch.failed_count,
        status=batch.status,
        csv_path="private",
        csv_url=(
            "/api/upload-batches/"
            f"{batch.id}/csv"
        ),
        items=result.items,
    ), 201


@bp.get(
    "/upload-batches/"
    "<int:batch_id>/csv"
)
@require_roles("ADMIN", "DOCTOR")
def download_batch_csv(batch_id):

    batch = db.session.get(
        UploadBatch,
        batch_id,
    )

    if not batch:
        abort(404)

    visible_case_or_404(
        batch.case_id
    )

    if not batch.csv_path:
        abort(404)

    upload_root = Path(
        current_app.config[
            "UPLOAD_FOLDER"
        ]
    ).resolve()

    csv_path = Path(
        batch.csv_path
    ).resolve()

    if (
        upload_root
        not in csv_path.parents
        or not csv_path.is_file()
    ):
        abort(404)

    return send_file(
        csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=(
            f"batch_{batch.id}.csv"
        ),
    )


@bp.get(
    "/upload-batches/"
    "<int:batch_id>/analysis.csv"
)
@require_roles("ADMIN", "DOCTOR")
def download_batch_analysis_csv(batch_id):
    batch = db.session.get(
        UploadBatch,
        batch_id,
    )

    if not batch:
        abort(404)

    visible_case_or_404(
        batch.case_id
    )

    return send_file(
        BytesIO(
            AnalysisCsvService.render(batch)
        ),
        mimetype="text/csv",
        as_attachment=True,
        download_name=(
            f"batch_{batch.id}_analysis.csv"
        ),
    )


@bp.get(
    "/upload-batches/"
    "<int:batch_id>/analysis.xlsx"
)
@require_roles("ADMIN", "DOCTOR")
def download_batch_analysis_excel(batch_id):
    batch = db.session.get(
        UploadBatch,
        batch_id,
    )

    if not batch:
        abort(404)

    visible_case_or_404(
        batch.case_id
    )

    return send_file(
        BytesIO(
            AnalysisExcelService(
                current_app
            ).render(batch)
        ),
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        as_attachment=True,
        download_name=(
            f"batch_{batch.id}_analysis.xlsx"
        ),
    )
