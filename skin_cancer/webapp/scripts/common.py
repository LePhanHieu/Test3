"""Hàm dùng chung cho các script ONNX / INT8."""

import sys
from pathlib import Path

# Đảm bảo stdout / stderr luôn dùng UTF-8 trên mọi hệ thống (tránh cp1252 trên Windows)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

# scripts/ -> webapp/ -> skin_cancer/ -> checkpoints/
CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"

CLASSES = ["MEL", "NV", "BCC", "AK", "BKL", "DF", "VASC", "SCC"]
MALIGNANT = ["MEL", "BCC", "SCC", "AK"]


def load_samples(csv_path, root, n, seed=42):
    """Lấy ngẫu nhiên n ảnh từ train.csv / test.csv.

    Ảnh nằm ở  root/<tên lớp>/<tên file>.jpg  (đúng cấu trúc ISIC2019 của đồ án).
    Trả về list (đường dẫn ảnh, tên lớp).
    """
    df = pd.read_csv(csv_path)
    df = df.sample(n=min(n, len(df)), random_state=seed)

    samples = []
    for _, row in df.iterrows():
        # img_path trong csv là đường dẫn Windows của máy cũ, chỉ lấy tên file
        filename = str(row["img_path"]).replace("\\", "/").split("/")[-1]
        path = Path(root) / row["label_name"] / filename
        if path.exists():
            samples.append((path, row["label_name"]))

    if not samples:
        raise SystemExit(f"Không tìm thấy ảnh nào trong {root}. Kiểm tra lại --root.")
    print(f"Đã tìm thấy {len(samples)}/{len(df)} ảnh.")
    return samples
