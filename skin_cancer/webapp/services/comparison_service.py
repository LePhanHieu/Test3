"""Image comparison metrics for the doctor timeline comparison view."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ComparisonResult:
    area_change_percent: float
    color_variance_percent: float
    before_area_ratio: float
    after_area_ratio: float
    before_risk_score: float
    after_risk_score: float

    @property
    def risk_change_percent(self) -> float:
        return self.after_risk_score - self.before_risk_score

    @property
    def progression(self) -> str:
        change = self.risk_change_percent
        if change >= 5:
            return "Có dấu hiệu tăng"
        if change <= -5:
            return "Có dấu hiệu cải thiện"
        return "Tương đối ổn định"


class ComparisonService:
    """Compute comparable visual metrics without creating database records."""

    def compare(self, before_bytes: bytes, after_bytes: bytes) -> ComparisonResult:
        before = self._decode(before_bytes)
        after = self._decode(after_bytes)
        target_size = (before.shape[1], before.shape[0])
        after = cv2.resize(after, target_size, interpolation=cv2.INTER_AREA)

        before_ratio = self._lesion_ratio(before)
        after_ratio = self._lesion_ratio(after)
        if before_ratio is None or after_ratio is None:
            raise ValueError(
                "Không nhận diện được vùng tổn thương rõ ràng trong một hoặc cả hai ảnh."
            )

        area_change = ((after_ratio - before_ratio) / before_ratio) * 100
        color_variance = float(
            np.mean(cv2.absdiff(before.astype(np.float32), after.astype(np.float32)))
            / 255
            * 100
        )
        before_risk = self._risk_score(before_ratio, before)
        after_risk = self._risk_score(after_ratio, after)
        return ComparisonResult(
            area_change_percent=round(area_change, 2),
            color_variance_percent=round(color_variance, 2),
            before_area_ratio=round(before_ratio, 6),
            after_area_ratio=round(after_ratio, 6),
            before_risk_score=round(before_risk, 2),
            after_risk_score=round(after_risk, 2),
        )

    @staticmethod
    def _decode(data: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ValueError("Không thể đọc một trong hai ảnh đã chọn.")
        return image

    @staticmethod
    def _lesion_ratio(image: np.ndarray) -> float | None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        candidates = []
        for mode in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
            _, mask = cv2.threshold(blurred, 0, 255, mode | cv2.THRESH_OTSU)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            ratio = float(cv2.countNonZero(mask)) / mask.size
            if 0.001 <= ratio <= 0.90:
                candidates.append(ratio)
        if not candidates:
            return None
        return min(candidates, key=lambda value: abs(value - 0.15))

    @staticmethod
    def _risk_score(area_ratio: float, image: np.ndarray) -> float:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        saturation = float(np.mean(hsv[:, :, 1])) / 255
        contrast = min(float(np.std(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))) / 64, 1)
        return min(100.0, area_ratio * 100 * 0.65 + saturation * 25 + contrast * 10)
