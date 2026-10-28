from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, send_file
from ..extensions import db, limiter
from ..models import Analysis
from ..services.access import require_roles, visible_case_or_404
from ..services.measurement_service import MeasurementService


bp = Blueprint('measurements', __name__, url_prefix='/api')


def _delete_replaced_contour(path):
    if not path:
        return

    measurement_root = Path(
        current_app.config['MEASUREMENT_FOLDER']
    ).resolve()
    candidate = Path(path).resolve()
    if measurement_root not in candidate.parents:
        current_app.logger.warning(
            "Skipped contour cleanup outside measurement root: %s",
            candidate,
        )
        return

    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning(
            "Could not remove replaced contour: %s",
            candidate,
            exc_info=True,
        )


def measurement_json(analysis, result=None):
    return {
        "analysis_id": analysis.id,
        "case_id": analysis.case_id,
        "case_image_id": analysis.case_image_id,
        "status": analysis.status,

        "error_code": (
            result.error_code
            if result
            else None
        ),

        "error_message":
            analysis.error_message,

        "lesion_area_px":
            analysis.lesion_area_px,

        "lesion_perimeter_px":
            analysis.lesion_perimeter_px,

        "lesion_ratio":
            analysis.lesion_ratio,

        "bbox_x":
            analysis.bbox_x,

        "bbox_y":
            analysis.bbox_y,

        "bbox_width":
            analysis.bbox_width,

        "bbox_height":
            analysis.bbox_height,

        # Không trả đường dẫn vật lý ra frontend
        "contour_url": (
            f"/api/analyses/"
            f"{analysis.id}/contour"
            if analysis.contour_path
            else None
        ),

        "units": {
            "area": "px²",
            "perimeter": "px",
            "ratio": "fraction",
        },
    }


@bp.post('/analyses/<int:analysis_id>/measure')
@limiter.limit(
    lambda: current_app.config["RATELIMIT_EXPENSIVE"]
)
@require_roles('ADMIN', 'DOCTOR')
def measure_analysis(analysis_id):
    analysis = db.session.get(Analysis, analysis_id)
    if not analysis:
        abort(404)
    case = visible_case_or_404(analysis.case_id)
    image = analysis.image
    previous_contour_path = analysis.contour_path
    result = None
    try:
        analysis.status = 'PROCESSING'
        analysis.error_message = None
        analysis.started_at = datetime.now(timezone.utc)
        db.session.flush()

        source_path = Path(image.image_path).resolve() if image and image.image_path else Path('')
        result = MeasurementService().measure(
            source_path, current_app.config['MEASUREMENT_FOLDER']
        )
        analysis.status = result.status
        analysis.completed_at = datetime.now(timezone.utc)
        analysis.error_message = result.error_message
        if result.status == 'COMPLETED':
            analysis.lesion_area_px = result.lesion_area_px
            analysis.lesion_perimeter_px = result.lesion_perimeter_px
            analysis.lesion_ratio = result.lesion_ratio
            analysis.bbox_x = result.bbox_x
            analysis.bbox_y = result.bbox_y
            analysis.bbox_width = result.bbox_width
            analysis.bbox_height = result.bbox_height
            analysis.contour_path = result.contour_path
            case.status = 'ANALYZED'
        else:
            analysis.lesion_area_px = None
            analysis.lesion_perimeter_px = None
            analysis.lesion_ratio = None
            analysis.bbox_x = None
            analysis.bbox_y = None
            analysis.bbox_width = None
            analysis.bbox_height = None
            analysis.contour_path = None
        db.session.commit()
        if previous_contour_path != analysis.contour_path:
            _delete_replaced_contour(
                previous_contour_path
            )
    except Exception:
        db.session.rollback()
        if result and result.contour_path:
            Path(result.contour_path).unlink(missing_ok=True)
        raise
    return jsonify(measurement_json(analysis, result))

@bp.get(
    "/analyses/"
    "<int:analysis_id>/contour"
)
@require_roles("ADMIN", "DOCTOR")
def get_analysis_contour(analysis_id):

    analysis = db.session.get(
        Analysis,
        analysis_id,
    )

    if not analysis:
        abort(404)

    # Kiểm tra Doctor/Admin có quyền
    # xem Case này hay không
    visible_case_or_404(
        analysis.case_id
    )

    if not analysis.contour_path:
        abort(
            404,
            description=(
                "Analysis chưa có "
                "ảnh contour."
            ),
        )

    measurement_root = Path(
        current_app.config[
            "MEASUREMENT_FOLDER"
        ]
    ).resolve()

    contour_path = Path(
        analysis.contour_path
    ).resolve()

    # Không cho truy cập file
    # ngoài measurement folder
    if (
        contour_path
        != measurement_root
        and measurement_root
        not in contour_path.parents
    ):
        abort(404)

    if not contour_path.is_file():
        abort(
            404,
            description=(
                "Không tìm thấy "
                "ảnh contour."
            ),
        )

    return send_file(
        contour_path,
        mimetype="image/png",
        as_attachment=False,
    )
    
    
    

