"""Task 1: API lưu / xoá vùng focus của một ảnh."""

from flask import Blueprint, abort, jsonify, request

from ..extensions import db
from ..models import CaseImage
from ..services.access import require_roles, visible_case_or_404
from ..services.focus_region import parse_polygon

bp = Blueprint("focus_region", __name__, url_prefix="/api")


def _get_case_image(case_image_id):
    case_image = db.session.get(CaseImage, case_image_id)
    if case_image is None:
        abort(404)
    visible_case_or_404(case_image.case_id)  # kiểm tra quyền xem ca bệnh
    return case_image


@bp.put("/case-images/<int:case_image_id>/focus-region")
@require_roles("ADMIN", "DOCTOR")
def save_focus_region(case_image_id):
    case_image = _get_case_image(case_image_id)
    try:
        points = parse_polygon(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    case_image.focus_region = {"points": points}
    db.session.commit()
    return jsonify(ok=True, focus_region=case_image.focus_region)


@bp.delete("/case-images/<int:case_image_id>/focus-region")
@require_roles("ADMIN", "DOCTOR")
def delete_focus_region(case_image_id):
    case_image = _get_case_image(case_image_id)
    case_image.focus_region = None
    db.session.commit()
    return jsonify(ok=True)
