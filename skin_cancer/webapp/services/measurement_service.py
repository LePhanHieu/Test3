"""
Independent OpenCV contour measurement for dermoscopy images.

- Không phụ thuộc EfficientNet hoặc Grad-CAM.
- Đo lường vẫn nằm trong hệ tọa độ pixel của ảnh gốc.
- Thử cả Otsu Binary và Binary Inverted để tăng độ ổn định.
- Không loại bỏ ngay contour chỉ vì chạm biên.
- Loại vùng quá nhỏ hoặc gần như chiếm toàn bộ ảnh.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

import cv2


# ============================================================
# RESULT
# ============================================================

@dataclass(frozen=True)
class MeasurementResult:
    status: str

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    lesion_area_px: Optional[float] = None
    lesion_perimeter_px: Optional[float] = None
    lesion_ratio: Optional[float] = None

    bbox_x: Optional[int] = None
    bbox_y: Optional[int] = None
    bbox_width: Optional[int] = None
    bbox_height: Optional[int] = None

    contour_path: Optional[str] = None


# ============================================================
# SERVICE
# ============================================================

class MeasurementService:

    def __init__(
        self,
        min_area_fraction=0.001,
        max_area_fraction=0.90,
        blur_kernel=5,
        morph_kernel=5,
        border_margin_fraction=0.01,
    ):
        """
        min_area_fraction:
            Loại contour quá nhỏ.

        max_area_fraction:
            Không chọn contour chiếm gần toàn bộ ảnh.
            Điều này giúp tránh chọn background hoặc
            viền tròn của dermoscope.

        border_margin_fraction:
            Khoảng biên dùng để đánh giá contour chạm cạnh.
            Chạm cạnh không còn bị loại ngay mà chỉ bị trừ điểm.
        """

        self.min_area_fraction = float(
            min_area_fraction
        )

        self.max_area_fraction = float(
            max_area_fraction
        )

        self.blur_kernel = self._odd_kernel(
            blur_kernel
        )

        self.morph_kernel = self._odd_kernel(
            morph_kernel
        )

        self.border_margin_fraction = float(
            border_margin_fraction
        )


    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _odd_kernel(value):

        value = max(
            3,
            int(value),
        )

        return (
            value
            if value % 2
            else value + 1
        )


    # ========================================================
    # MAIN
    # ========================================================

    def measure(
        self,
        image_path,
        output_dir,
    ) -> MeasurementResult:

        source = Path(
            image_path
        ).resolve()

        # ----------------------------------------------------
        # READ IMAGE
        # ----------------------------------------------------

        image = cv2.imread(
            str(source),
            cv2.IMREAD_COLOR,
        )

        if image is None:

            return MeasurementResult(
                status="FAILED",
                error_code="IMAGE_READ_ERROR",
                error_message=(
                    "Không thể đọc ảnh đầu vào"
                ),
            )

        height, width = (
            image.shape[:2]
        )

        if width <= 0 or height <= 0:

            return MeasurementResult(
                status="FAILED",
                error_code="INVALID_IMAGE_SIZE",
                error_message=(
                    "Ảnh có kích thước không hợp lệ"
                ),
            )


        # ----------------------------------------------------
        # GRAYSCALE + BLUR
        # ----------------------------------------------------

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        blurred = cv2.GaussianBlur(
            gray,
            (
                self.blur_kernel,
                self.blur_kernel,
            ),
            0,
        )


        # ----------------------------------------------------
        # CREATE TWO OTSU MASKS
        #
        # Không biết trước lesion sáng hay tối hơn nền,
        # vì vậy thử cả hai polarity.
        # ----------------------------------------------------

        _, binary_inv = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY_INV
            + cv2.THRESH_OTSU,
        )

        _, binary = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY
            + cv2.THRESH_OTSU,
        )


        # ----------------------------------------------------
        # MORPHOLOGY
        # ----------------------------------------------------

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (
                self.morph_kernel,
                self.morph_kernel,
            ),
        )

        masks = [
            self._clean_mask(
                binary_inv,
                kernel,
            ),
            self._clean_mask(
                binary,
                kernel,
            ),
        ]


        # ----------------------------------------------------
        # FIND BEST CONTOUR FROM BOTH MASKS
        # ----------------------------------------------------

        contour = self._select_best_contour(
            masks,
            width,
            height,
        )

        if contour is None:

            return MeasurementResult(
                status="FAILED",
                error_code="NO_CONTOUR",
                error_message=(
                    "Không tìm thấy contour "
                    "tổn thương phù hợp"
                ),
            )


        # ----------------------------------------------------
        # MEASURE
        # ----------------------------------------------------

        area = float(
            cv2.contourArea(
                contour
            )
        )

        perimeter = float(
            cv2.arcLength(
                contour,
                True,
            )
        )

        (
            x,
            y,
            box_width,
            box_height,
        ) = cv2.boundingRect(
            contour
        )

        image_area = float(
            width * height
        )

        ratio = (
            area / image_area
            if image_area > 0
            else 0.0
        )


        # ----------------------------------------------------
        # CREATE OVERLAY
        # ----------------------------------------------------

        overlay = image.copy()

        # Tô vùng lesion nhẹ để dễ nhìn
        filled = image.copy()

        cv2.drawContours(
            filled,
            [contour],
            -1,
            (0, 190, 0),
            thickness=-1,
        )

        overlay = cv2.addWeighted(
            filled,
            0.18,
            overlay,
            0.82,
            0,
        )


        # Độ dày theo kích thước ảnh
        thickness = max(
            2,
            int(
                min(
                    width,
                    height,
                ) * 0.003
            ),
        )


        # contour xanh
        cv2.drawContours(
            overlay,
            [contour],
            -1,
            (0, 255, 0),
            thickness,
            lineType=cv2.LINE_AA,
        )


        # bounding box đỏ
        cv2.rectangle(
            overlay,
            (
                x,
                y,
            ),
            (
                x + box_width,
                y + box_height,
            ),
            (0, 0, 255),
            thickness,
            lineType=cv2.LINE_AA,
        )


        # ----------------------------------------------------
        # LABEL
        # ----------------------------------------------------

        font_scale = max(
            0.45,
            min(
                width,
                height,
            ) / 1000.0,
        )

        text_thickness = max(
            1,
            thickness // 2,
        )

        info_lines = [
            f"Area: {area:.0f} px2",
            (
                "Perimeter: "
                f"{perimeter:.1f} px"
            ),
            (
                "Ratio: "
                f"{ratio * 100:.2f}%"
            ),
        ]

        text_x = max(
            10,
            x,
        )

        text_y = max(
            25,
            y - 10,
        )

        line_height = int(
            24 * font_scale
            + 12
        )

        for index, text in enumerate(
            info_lines
        ):

            pos_y = (
                text_y
                + index
                * line_height
            )

            # nền chữ
            (
                text_size,
                _,
            ) = cv2.getTextSize(
                text,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                text_thickness,
            )

            text_width = (
                text_size[0]
            )

            text_height = (
                text_size[1]
            )

            cv2.rectangle(
                overlay,
                (
                    text_x - 4,
                    pos_y
                    - text_height
                    - 5,
                ),
                (
                    text_x
                    + text_width
                    + 5,
                    pos_y + 5,
                ),
                (0, 0, 0),
                thickness=-1,
            )

            cv2.putText(
                overlay,
                text,
                (
                    text_x,
                    pos_y,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                text_thickness,
                lineType=cv2.LINE_AA,
            )


        # ----------------------------------------------------
        # SAVE OVERLAY
        # ----------------------------------------------------

        output_root = Path(
            output_dir
        ).resolve()

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            output_root
            / (
                "contour_"
                f"{uuid4().hex}.png"
            )
        ).resolve()


        # chống path traversal
        if (
            output_root
            not in output_path.parents
        ):

            return MeasurementResult(
                status="FAILED",
                error_code=(
                    "OVERLAY_WRITE_ERROR"
                ),
                error_message=(
                    "Đường dẫn ảnh contour "
                    "không hợp lệ"
                ),
            )


        saved = cv2.imwrite(
            str(output_path),
            overlay,
        )

        if not saved:

            return MeasurementResult(
                status="FAILED",
                error_code=(
                    "OVERLAY_WRITE_ERROR"
                ),
                error_message=(
                    "Không thể lưu ảnh contour"
                ),
            )


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        return MeasurementResult(
            status="COMPLETED",

            lesion_area_px=area,

            lesion_perimeter_px=(
                perimeter
            ),

            lesion_ratio=ratio,

            bbox_x=int(x),
            bbox_y=int(y),

            bbox_width=int(
                box_width
            ),

            bbox_height=int(
                box_height
            ),

            contour_path=str(
                output_path
            ),
        )


    # ========================================================
    # MASK CLEANING
    # ========================================================

    @staticmethod
    def _clean_mask(
        mask,
        kernel,
    ):

        # loại nhiễu nhỏ
        opened = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            kernel,
            iterations=1,
        )

        # nối các vùng lesion bị đứt
        cleaned = cv2.morphologyEx(
            opened,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=2,
        )

        return cleaned


    # ========================================================
    # SELECT BEST CONTOUR
    # ========================================================

    def _select_best_contour(
        self,
        masks,
        width,
        height,
    ):

        image_area = float(
            width * height
        )

        min_area = max(
            10.0,
            image_area
            * self.min_area_fraction,
        )

        max_area = (
            image_area
            * self.max_area_fraction
        )

        candidates = []


        # thử contour từ cả mask normal và inverse
        for mask in masks:

            contours, _ = (
                cv2.findContours(
                    mask,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
            )

            for contour in contours:

                score = (
                    self._score_contour(
                        contour,
                        width,
                        height,
                        min_area,
                        max_area,
                    )
                )

                if score is None:
                    continue

                candidates.append(
                    (
                        score,
                        contour,
                    )
                )


        if not candidates:
            return None


        # score cao nhất
        candidates.sort(
            key=lambda item:
                item[0],
            reverse=True,
        )

        return candidates[0][1]


    # ========================================================
    # SCORE CONTOUR
    # ========================================================

    def _score_contour(
        self,
        contour,
        width,
        height,
        min_area,
        max_area,
    ):

        image_area = float(
            width * height
        )

        area = float(
            cv2.contourArea(
                contour
            )
        )


        # quá nhỏ
        if area < min_area:
            return None


        # gần như toàn bộ ảnh
        if area > max_area:
            return None


        (
            x,
            y,
            box_width,
            box_height,
        ) = cv2.boundingRect(
            contour
        )


        if (
            box_width <= 2
            or box_height <= 2
        ):
            return None


        bbox_area = float(
            box_width
            * box_height
        )

        if bbox_area <= 0:
            return None


        # ----------------------------------------------------
        # AREA FRACTION
        # ----------------------------------------------------

        area_fraction = (
            area / image_area
        )


        # ----------------------------------------------------
        # EXTENT
        #
        # Tỷ lệ contour / bounding box
        # ----------------------------------------------------

        extent = (
            area / bbox_area
        )


        # ----------------------------------------------------
        # SOLIDITY
        # ----------------------------------------------------

        hull = cv2.convexHull(
            contour
        )

        hull_area = float(
            cv2.contourArea(
                hull
            )
        )

        solidity = (
            area / hull_area
            if hull_area > 0
            else 0.0
        )


        # ----------------------------------------------------
        # CENTER SCORE
        #
        # Dermoscopy thường đặt lesion gần vùng trung tâm.
        # Chỉ dùng làm score, không phải điều kiện bắt buộc.
        # ----------------------------------------------------

        center_x = (
            x
            + box_width / 2.0
        )

        center_y = (
            y
            + box_height / 2.0
        )

        dx = abs(
            center_x
            - width / 2.0
        ) / max(
            width / 2.0,
            1.0,
        )

        dy = abs(
            center_y
            - height / 2.0
        ) / max(
            height / 2.0,
            1.0,
        )

        center_distance = min(
            1.0,
            (
                (
                    dx * dx
                    + dy * dy
                )
                ** 0.5
            )
            / 1.41421356237,
        )

        center_score = (
            1.0
            - center_distance
        )
        # ----------------------------------------------------
        # BORDER
        #
        # Khác code cũ:
        # chạm biên KHÔNG bị loại ngay.
        # ----------------------------------------------------

        border_sides = (
            self._count_border_sides(
                contour,
                width,
                height,
            )
        )


        # Nếu vùng lớn và gần như là toàn background,
        # chạm 3-4 cạnh -> loại.
        if (
            border_sides >= 3
            and area_fraction > 0.25
        ):
            return None


        # ----------------------------------------------------
        # AREA SCORE
        #
        # Khuyến khích vùng đủ lớn nhưng không ép lesion
        # phải có một kích thước cố định.
        # ----------------------------------------------------

        area_score = min(
            1.0,
            area_fraction / 0.20,
        )


        # ----------------------------------------------------
        # FINAL SCORE
        # ----------------------------------------------------

        score = (
            2.2 * center_score
            + 1.3 * area_score
            + 0.45 * solidity
            + 0.30 * extent
        )


        # Chạm biên chỉ bị trừ điểm
        score -= (
            border_sides
            * 0.35
        )


        # vùng cực lớn có nguy cơ là background
        if area_fraction > 0.65:
            score -= 1.5

        elif area_fraction > 0.45:
            score -= 0.6


        return score


    # ========================================================
    # BORDER CHECK
    # ========================================================

    def _count_border_sides(
        self,
        contour,
        width,
        height,
    ):

        (
            x,
            y,
            box_width,
            box_height,
        ) = cv2.boundingRect(
            contour
        )

        margin = max(
            1,
            int(
                min(
                    width,
                    height,
                )
                * self.border_margin_fraction
            ),
        )

        left = (
            x <= margin
        )

        top = (
            y <= margin
        )

        right = (
            x + box_width
            >= width - margin
        )

        bottom = (
            y + box_height
            >= height - margin
        )

        return sum(
            [
                left,
                top,
                right,
                bottom,
            ]
        )