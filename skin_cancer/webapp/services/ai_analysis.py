"""Database state transitions for AI analysis execution."""

from ..extensions import db
from ..models import Analysis, CaseImage
from ..models.base import utcnow


def mark_analysis_failed(
    analysis_id: int | None,
    case_image_id: int,
    error: Exception,
) -> None:
    """Persist an AI failure after rolling back incomplete inference output."""

    db.session.rollback()

    analysis = (
        db.session.get(Analysis, analysis_id)
        if analysis_id is not None
        else None
    )
    case_image = db.session.get(CaseImage, case_image_id)

    if analysis is not None:
        analysis.status = "FAILED"
        analysis.completed_at = utcnow()
        analysis.error_message = (
            f"{type(error).__name__}: {error}"
        )[:2000]

    if case_image is not None and case_image.status == "PROCESSING":
        case_image.status = "UPLOADED"

    db.session.commit()
