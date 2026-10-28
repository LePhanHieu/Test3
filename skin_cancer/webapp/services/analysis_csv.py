"""Generate a current, batch-scoped analysis export without exposing paths."""

import csv
import io
from datetime import timezone

from .analysis_export_data import binary_label, latest, load_batch_graph
from .batch_upload import spreadsheet_safe

CLASS_NAMES = ("MEL", "NV", "BCC", "AK", "BKL", "DF", "VASC", "SCC")

CSV_COLUMNS = (
    "batch_id",
    "case_code",
    "image_id",
    "original_filename",
    "image_status",
    "image_error_message",
    "uploaded_at",
    "analysis_id",
    "analysis_status",
    "analysis_error_message",
    "analysis_started_at",
    "analysis_completed_at",
    "model_name",
    "inference_time_ms",
    "ai_binary_result",
    "ai_binary_probability",
    "predicted_class",
    "predicted_probability",
    *(f"probability_{name}" for name in CLASS_NAMES),
    "result_created_at",
    "lesion_area_px",
    "lesion_perimeter_px",
    "lesion_ratio",
    "bbox_x",
    "bbox_y",
    "bbox_width",
    "bbox_height",
    "review_status",
    "doctor_conclusion",
    "clinical_note",
    "recommendation",
    "reviewer_name",
    "review_updated_at",
)


def _timestamp(value):
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat()}Z"


def _public_analysis_error(value):
    return "Phân tích thất bại" if value else ""


class AnalysisCsvService:
    """Serialize the latest persisted analysis state for one upload batch."""

    @classmethod
    def rows(cls, batch):
        batch = load_batch_graph(batch.id)
        rows = [cls._image_row(batch, image) for image in batch.images]
        rows.extend(
            cls._rejected_rows(
                batch,
                {image.id for image in batch.images},
            )
        )
        return rows

    @classmethod
    def render(cls, batch):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for row in cls.rows(batch):
            writer.writerow(
                {column: spreadsheet_safe(row.get(column, "")) for column in CSV_COLUMNS}
            )
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def _image_row(batch, image):
        row = {column: "" for column in CSV_COLUMNS}
        row.update(
            batch_id=batch.id,
            case_code=batch.case.case_code,
            image_id=image.id,
            original_filename=image.original_filename,
            image_status=image.status,
            image_error_message=image.error_message or "",
            uploaded_at=_timestamp(image.uploaded_at),
        )

        analysis = latest(image.analyses)
        if analysis is None:
            return row

        row.update(
            analysis_id=analysis.id,
            analysis_status=analysis.status,
            analysis_error_message=_public_analysis_error(
                analysis.error_message
            ),
            analysis_started_at=_timestamp(analysis.started_at),
            analysis_completed_at=_timestamp(analysis.completed_at),
            lesion_area_px=analysis.lesion_area_px,
            lesion_perimeter_px=analysis.lesion_perimeter_px,
            lesion_ratio=analysis.lesion_ratio,
            bbox_x=analysis.bbox_x,
            bbox_y=analysis.bbox_y,
            bbox_width=analysis.bbox_width,
            bbox_height=analysis.bbox_height,
        )

        result = latest(analysis.results)
        if result is not None:
            probabilities = (
                result.class_probabilities
                if isinstance(result.class_probabilities, dict)
                else {}
            )
            row.update(
                model_name=result.model_name,
                inference_time_ms=result.inference_time_ms,
                ai_binary_result=binary_label(result.binary_result),
                ai_binary_probability=result.binary_probability,
                predicted_class=result.predicted_class,
                predicted_probability=result.predicted_probability,
                result_created_at=_timestamp(result.created_at),
            )
            row.update(
                {
                    f"probability_{name}": probabilities.get(name, "")
                    for name in CLASS_NAMES
                }
            )

        review = latest(analysis.reviews)
        if review is not None:
            row.update(
                review_status=review.review_status,
                doctor_conclusion=review.doctor_conclusion or "",
                clinical_note=review.clinical_note or "",
                recommendation=review.recommendation or "",
                reviewer_name=review.doctor.full_name,
                review_updated_at=_timestamp(review.updated_at),
            )
        return row

    @staticmethod
    def _rejected_rows(batch, represented_image_ids):
        rows = []
        for item in batch.item_results or []:
            if (
                item.get("status") == "UPLOADED"
                or item.get("case_image_id") in represented_image_ids
            ):
                continue
            row = {column: "" for column in CSV_COLUMNS}
            row.update(
                batch_id=batch.id,
                case_code=batch.case.case_code,
                original_filename=(
                    item.get("original_filename") or item.get("filename") or ""
                ),
                image_status=item.get("status") or "FAILED",
                image_error_message=item.get("error_message") or "",
            )
            rows.append(row)
        return rows
