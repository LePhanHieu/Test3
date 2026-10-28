"""Task 2: Kiểm tra chất lượng ảnh trước khi phân tích."""

import cv2
import numpy as np

# Các ngưỡng này chỉnh được, thử với vài ảnh thật rồi sửa cho hợp
MIN_SIZE = 224  # cạnh ngắn nhất (px)
BLUR_THRESHOLD = 10.0  # variance of Laplacian, ảnh mờ thực sự < 10 (test_mo: 0.8)
DARK_THRESHOLD = 40  # độ sáng trung bình (0-255), thấp hơn = quá tối
BRIGHT_THRESHOLD = 215  # cao hơn = quá sáng


def check_image_quality(pil_img):
    """Trả về dict: {"ok": bool, "warnings": [str], "metrics": {...}}"""
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    height, width = gray.shape
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = float(gray.mean())

    warnings = []

    if min(width, height) < MIN_SIZE:
        warnings.append(
            f"Ảnh quá nhỏ ({width}x{height}), nên dùng ảnh từ {MIN_SIZE}px trở lên."
        )
    if blur_score < BLUR_THRESHOLD:
        warnings.append("Ảnh bị mờ, kết quả có thể kém chính xác.")
    if brightness < DARK_THRESHOLD:
        warnings.append("Ảnh quá tối.")
    elif brightness > BRIGHT_THRESHOLD:
        warnings.append("Ảnh quá sáng.")

    return {
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "metrics": {
            "width": width,
            "height": height,
            "blur_score": round(float(blur_score), 1),
            "brightness": round(brightness, 1),
        },
    }
