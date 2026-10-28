"""Task 3: Cảnh báo "model không chắc chắn" từ xác suất softmax."""

import math

# Chỉnh ngưỡng bằng tập val: xem các ca model đoán sai thường có margin/entropy bao nhiêu
MARGIN_THRESHOLD = 0.20  # top-1 hơn top-2 ít hơn 20% -> không chắc
ENTROPY_THRESHOLD = 0.60  # entropy chuẩn hóa (0..1) cao hơn -> không chắc


def check_uncertainty(probs):
    """probs: dict {tên_lớp: xác suất} hoặc list xác suất."""
    values = list(probs.values()) if isinstance(probs, dict) else list(probs)

    top = sorted(values, reverse=True)
    margin = top[0] - top[1]

    # Entropy chia cho log(số lớp) để về thang 0..1
    entropy = -sum(p * math.log(p) for p in values if p > 0)
    entropy_norm = entropy / math.log(len(values))

    is_uncertain = margin < MARGIN_THRESHOLD or entropy_norm > ENTROPY_THRESHOLD

    return {
        "is_uncertain": is_uncertain,
        "margin": round(margin, 3),
        "entropy": round(entropy_norm, 3),
        "message": "Ca này khó, nên hỏi bác sĩ." if is_uncertain else None,
    }
