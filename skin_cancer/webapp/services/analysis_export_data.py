"""Shared database loading helpers for batch analysis exports."""

from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Analysis, CaseImage, DoctorReview, UploadBatch


def latest(records):
    return max(records, key=lambda record: record.id, default=None)


def binary_label(value):
    if value == 0:
        return "BENIGN"
    if value == 1:
        return "MALIGNANT"
    return ""


def load_batch_graph(batch_id):
    image_analyses = selectinload(UploadBatch.images).selectinload(
        CaseImage.analyses
    )
    statement = (
        db.select(UploadBatch)
        .where(UploadBatch.id == batch_id)
        .options(
            selectinload(UploadBatch.case),
            image_analyses.selectinload(Analysis.results),
            image_analyses.selectinload(Analysis.reviews).selectinload(
                DoctorReview.doctor
            ),
        )
    )
    return db.session.scalar(statement)
