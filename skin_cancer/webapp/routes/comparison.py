import hashlib
import io

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from PIL import Image, UnidentifiedImageError

from ..services.access import require_roles
from ..services.comparison_service import ComparisonService
from ..services.image_upload import UploadTooLarge, read_limited_upload


bp = Blueprint("comparison", __name__, url_prefix="/api")

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _read_image_upload(field_name: str) -> bytes:
    upload = request.files.get(field_name)
    if upload is None or not upload.filename:
        raise ValueError(f"Vui lòng chọn ảnh {field_name}.")
    if upload.mimetype not in ALLOWED_MIME_TYPES:
        raise ValueError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.")
    data = read_limited_upload(
        upload.stream,
        current_app.config["BATCH_MAX_FILE_BYTES"],
    )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            if image.width < 32 or image.height < 32:
                raise ValueError("Ảnh phải có kích thước tối thiểu 32 x 32 pixel.")
            if image.width * image.height > current_app.config["BATCH_MAX_IMAGE_PIXELS"]:
                raise ValueError("Ảnh vượt quá giới hạn số pixel cho phép.")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Tệp đã chọn không phải là ảnh hợp lệ.") from exc
    return data


@bp.post("/compare")
@require_roles("DOCTOR", "ADMIN")
def compare_images():
    try:
        before = _read_image_upload("before")
        after = _read_image_upload("after")
        if hashlib.sha256(before).digest() == hashlib.sha256(after).digest():
            raise ValueError("Ảnh Trước và Sau phải là hai ảnh khác nhau.")
        result = ComparisonService().compare(before, after)
    except (UploadTooLarge, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        current_app.logger.exception(
            "Image comparison failed for doctor %s",
            current_user.id,
        )
        return jsonify(error="Không thể hoàn tất pipeline so sánh ảnh. Vui lòng thử lại."), 500

    return jsonify(
        area_change_percent=result.area_change_percent,
        color_variance_percent=result.color_variance_percent,
        progression=result.progression,
        risk_change_percent=round(result.risk_change_percent, 2),
        before_risk_score=result.before_risk_score,
        after_risk_score=result.after_risk_score,
    )
