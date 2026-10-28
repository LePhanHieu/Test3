"""Validation, private storage, and CSV export for B1 batch uploads."""

import io
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import warnings

import pandas as pd
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from ..extensions import db
from ..models import CaseImage


CSV_COLUMNS = [
    "filename",
    "case_code",
    "analysis_id",
    "predicted_class",
    "predicted_probability",
    "lesion_area_px",
    "lesion_perimeter_px",
    "lesion_ratio",
    "status",
    "error_message",
]


ALLOWED = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

EXPECTED_IMAGE_FORMAT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

SPREADSHEET_FORMULA_PREFIXES = (
    "=",
    "+",
    "-",
    "@",
    "\t",
    "\r",
)


def spreadsheet_safe(value):
    if (
        isinstance(value, str)
        and value.startswith(
            SPREADSHEET_FORMULA_PREFIXES
        )
    ):
        return f"'{value}"
    return value


@dataclass
class BatchUploadResult:
    items: list[dict]
    rows: list[dict]

    @property
    def success_count(self):
        return sum(
            item["status"] == "UPLOADED"
            for item in self.items
        )

    @property
    def failed_count(self):
        return sum(
            item["status"] == "FAILED"
            for item in self.items
        )


class BatchUploadService:

    def __init__(self, app, batch, case, actor):
        self.app = app
        self.batch = batch
        self.case = case
        self.actor = actor

        self.upload_root = Path(
            app.config["UPLOAD_FOLDER"]
        ).resolve()

        self.max_file_bytes = int(
            app.config["BATCH_MAX_FILE_BYTES"]
        )

        self.max_image_pixels = int(
            app.config.get(
                "BATCH_MAX_IMAGE_PIXELS",
                25_000_000,
            )
        )

    def process(
        self,
        files: list[FileStorage],
    ) -> BatchUploadResult:

        image_dir = self.upload_root / "images"
        image_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        seen_hashes = set()
        created_paths = []

        items = []
        rows = []

        try:
            for file in files:

                item, row = self._process_one(
                    file,
                    image_dir,
                    seen_hashes,
                    created_paths,
                )

                items.append(item)
                rows.append(row)
        except Exception:
            for created_path in created_paths:
                created_path.unlink(
                    missing_ok=True
                )
            raise

        return BatchUploadResult(
            items=items,
            rows=rows,
        )

    def _process_one(
        self,
        file,
        image_dir,
        seen_hashes,
        created_paths,
    ):

        original = (
            file.filename or ""
        )[:255]

        extension = Path(
            original
        ).suffix.lower()

        item = {
            "case_image_id": None,
            "original_filename": original,
            "filename": "",
            "status": "FAILED",
            "error_message": None,
        }

        row = self._empty_row(item)

        data = b""
        path = ""

        error = self._validate_name_and_mime(
            original,
            extension,
            file.mimetype,
        )

        # ==========================================
        # FILE SIZE
        # ==========================================

        if error is None:

            data = file.stream.read(
                self.max_file_bytes + 1
            )

            if len(data) > self.max_file_bytes:
                error = (
                    "File exceeds maximum size of "
                    f"{self.max_file_bytes} bytes"
                )

        # ==========================================
        # DUPLICATE TRONG CÙNG BATCH
        # ==========================================

        digest = None

        if error is None:

            digest = sha256(data).hexdigest()

            if digest in seen_hashes:
                error = (
                    "Duplicate image content "
                    "in this batch"
                )
            else:
                seen_hashes.add(digest)

        # ==========================================
        # IMAGE VALIDATION
        # ==========================================

        if error is None:

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter(
                        "error",
                        Image.DecompressionBombWarning,
                    )

                    with Image.open(
                        io.BytesIO(data)
                    ) as image:
                        detected_format = (
                            image.format or ""
                        ).upper()
                        width, height = image.size
                        image.verify()

                expected_format = (
                    EXPECTED_IMAGE_FORMAT[
                        extension
                    ]
                )

                if detected_format != expected_format:
                    error = (
                        "Decoded image format does not "
                        "match file extension"
                    )
                elif width * height > self.max_image_pixels:
                    error = (
                        "Image exceeds maximum pixel "
                        f"count of {self.max_image_pixels}"
                    )

            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombWarning,
                Image.DecompressionBombError,
            ):
                error = (
                    "Uploaded file is not "
                    "a valid image"
                )

        # ==========================================
        # SAVE FILE
        # ==========================================

        if error is None:

            stored_name = (
                f"{uuid4()}{extension}"
            )

            destination = (
                image_dir / stored_name
            ).resolve()

            if image_dir not in destination.parents:

                error = "Invalid storage path"

            else:

                created_paths.append(
                    destination
                )
                destination.write_bytes(data)

                path = str(destination)

                item.update(
                    filename=stored_name,
                    status="UPLOADED",
                )

                row.update(
                    filename=stored_name,
                    status="UPLOADED",
                )

        # ==========================================
        # ERROR
        # ==========================================

        if error is not None:

            item["error_message"] = error
            row["error_message"] = error

        # ==========================================
        # DATABASE
        # ==========================================

        case_image = CaseImage(
            case_id=self.case.id,
            batch_id=self.batch.id,
            image_path=path,
            original_filename=(
                original or "unnamed-file"
            ),
            mime_type=(
                file.mimetype
                or "application/octet-stream"
            ),
            file_size=len(data),
            sha256_hash=(
                digest
                if digest
                else (
                    sha256(data).hexdigest()
                    if data
                    else None
                )
            ),
            uploaded_by=self.actor.id,
            status=item["status"],
            error_message=error,
        )

        db.session.add(case_image)

        # QUAN TRỌNG:
        # lấy ID trước khi response batch được tạo
        db.session.flush()

        item["case_image_id"] = case_image.id

        return item, row

    @staticmethod
    def _validate_name_and_mime(
        original,
        extension,
        mimetype,
    ):

        if not original:
            return "Filename is empty"

        expected_mime = ALLOWED.get(
            extension
        )

        if expected_mime is None:
            return (
                "Unsupported file extension"
            )

        if (
            mimetype
            and mimetype != expected_mime
        ):
            return (
                "MIME type does not match "
                "file extension"
            )

        return None

    def _empty_row(self, item):

        return {
            "filename": (
                item["filename"]
                or item["original_filename"]
            ),
            "case_code": self.case.case_code,
            "analysis_id": "",
            "predicted_class": "",
            "predicted_probability": "",
            "lesion_area_px": "",
            "lesion_perimeter_px": "",
            "lesion_ratio": "",
            "status": item["status"],
            "error_message": (
                item["error_message"] or ""
            ),
        }

    @staticmethod
    def write_csv(rows, path):

        output = Path(path).resolve()

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_rows = [
            {
                key: spreadsheet_safe(value)
                for key, value in row.items()
            }
            for row in rows
        ]

        pd.DataFrame.from_records(
            safe_rows,
            columns=CSV_COLUMNS,
        ).to_csv(
            output,
            index=False,
            encoding="utf-8",
        )
