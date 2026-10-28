"""Task 1: Focus vùng ảnh - bác sĩ vẽ polygon, model chỉ phân tích vùng đó."""

import cv2
import numpy as np
from PIL import Image

MIN_POINTS = 3
MAX_POINTS = 200
MIN_AREA = 0.01  # vùng phải chiếm ít nhất 1% diện tích ảnh


def parse_polygon(data):
    """Kiểm tra dữ liệu từ frontend: {"points": [[x, y], ...]}, x y trong 0..1.

    Dùng toạ độ chuẩn hoá (0..1) để không phụ thuộc kích thước ảnh hiển thị.
    Trả về list điểm hợp lệ, hoặc raise ValueError.
    """
    points = (data or {}).get("points")
    if not isinstance(points, list) or not (MIN_POINTS <= len(points) <= MAX_POINTS):
        raise ValueError(f"Cần từ {MIN_POINTS} đến {MAX_POINTS} điểm.")

    clean = []
    for p in points:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError("Toạ độ điểm không hợp lệ.")
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Toạ độ phải nằm trong khoảng 0..1.")
        clean.append([round(x, 4), round(y, 4)])

    # Diện tích polygon (công thức shoelace) để loại vùng quá nhỏ
    area = 0.0
    for i in range(len(clean)):
        x1, y1 = clean[i]
        x2, y2 = clean[(i + 1) % len(clean)]
        area += x1 * y2 - x2 * y1
    if abs(area) / 2 < MIN_AREA:
        raise ValueError("Vùng khoanh quá nhỏ.")

    return clean


def apply_focus_region(pil_img, region):
    """Cắt ảnh theo polygon. Không có vùng thì trả lại ảnh gốc.

    Cách làm: tô vùng ngoài polygon bằng màu trung bình của vùng trong,
    rồi crop theo hình chữ nhật bao quanh polygon.
    """
    if not region or not region.get("points"):
        return pil_img

    w, h = pil_img.size
    pts = np.array([[x * w, y * h] for x, y in region["points"]], dtype=np.int32)

    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    if not mask.any():
        return pil_img

    img = np.array(pil_img.convert("RGB"))
    img[mask == 0] = img[mask > 0].mean(axis=0).astype(np.uint8)

    x, y, bw, bh = cv2.boundingRect(pts)
    return Image.fromarray(img[y : y + bh, x : x + bw])
