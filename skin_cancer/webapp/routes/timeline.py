"""Task 4: Timeline tiến triển của một bệnh nhân qua nhiều lần chụp."""

from flask import Blueprint, jsonify
from flask_login import current_user
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Analysis, Case
from ..services.access import require_roles, visible_case_or_404, visible_cases

bp = Blueprint("timeline", __name__, url_prefix="/api")


def build_trend(points):
    """So lần đầu và lần cuối. Ngưỡng ±5% giống comparison_service."""
    if len(points) < 2:
        return None
    change = round(points[-1]["prob_malignant"] - points[0]["prob_malignant"], 1)
    if change >= 5:
        label = "Có dấu hiệu tăng"
    elif change <= -5:
        label = "Có dấu hiệu cải thiện"
    else:
        label = "Tương đối ổn định"
    return {"label": label, "change": change}


@bp.get("/cases/<int:case_id>/timeline")
@require_roles()
def case_timeline(case_id):
    case = visible_case_or_404(case_id)

    # Bệnh nhân có tài khoản: gộp mọi ca của họ. Bệnh nhân tạm: chỉ ca này.
    if case.patient_user_id:
        case_ids = db.session.scalars(
            visible_cases(current_user)
            .where(Case.patient_user_id == case.patient_user_id)
            .with_only_columns(Case.id)
        ).all()
    else:
        case_ids = [case.id]

    analyses = db.session.scalars(
        db.select(Analysis)
        .options(selectinload(Analysis.results), selectinload(Analysis.case))
        .where(Analysis.case_id.in_(case_ids), Analysis.status == "COMPLETED")
        .order_by(Analysis.created_at.asc(), Analysis.id.asc())
    ).all()

    points = []
    for analysis in analyses:
        result = next((r for r in analysis.results if r.predicted_class), None)
        if result is None:
            continue
        points.append(
            {
                "analysis_id": analysis.id,
                "case_code": analysis.case.case_code,
                "date": analysis.created_at.isoformat() + "Z",
                "predicted_class": result.predicted_class.upper(),
                "prob_malignant": round((result.binary_probability or 0) * 100, 1),
                "confidence": round((result.predicted_probability or 0) * 100, 1),
                "lesion_area_px": analysis.lesion_area_px,  # None nếu chưa đo
            }
        )

    return jsonify(points=points, trend=build_trend(points))
