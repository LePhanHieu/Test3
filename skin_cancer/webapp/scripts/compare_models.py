"""So sánh ONNX FP32 và INT8: kích thước, tốc độ, độ chính xác.

Chạy từ thư mục gốc project (dùng ảnh TEST):
    python -m skin_cancer.webapp.scripts.compare_models --csv skin_cancer/test.csv --root /duong/dan/isic2019
"""

import argparse
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

from skin_cancer.webapp.scripts.common import CKPT_DIR, CLASSES, MALIGNANT, load_samples
from skin_cancer.webapp.services.onnx_inference import preprocess_numpy


def make_session(name):
    return ort.InferenceSession(
        str(CKPT_DIR / name), providers=["CPUExecutionProvider"]
    )


def predict_all(session, inputs):
    return np.array([session.run(None, {"input": x})[0].argmax() for x in inputs])


def latency_ms(session, inputs, repeat=50):
    for x in inputs[:5]:  # chạy nóng máy
        session.run(None, {"input": x})
    start = time.perf_counter()
    for i in range(repeat):
        session.run(None, {"input": inputs[i % len(inputs)]})
    return (time.perf_counter() - start) / repeat * 1000


def compare(name, inputs, labels):
    fp32_file, int8_file = f"{name}.onnx", f"{name}_int8.onnx"
    fp32, int8 = make_session(fp32_file), make_session(int8_file)

    pred_fp32, pred_int8 = predict_all(fp32, inputs), predict_all(int8, inputs)
    agree = (pred_fp32 == pred_int8).mean() * 100
    acc_fp32 = (pred_fp32 == labels).mean() * 100
    acc_int8 = (pred_int8 == labels).mean() * 100

    print(f"\n=== {name} ===")
    print(f"{'':12}{'FP32':>10}{'INT8':>10}")
    print(
        f"{'Kích thước':12}{(CKPT_DIR / fp32_file).stat().st_size / 1e6:>8.1f}MB"
        f"{(CKPT_DIR / int8_file).stat().st_size / 1e6:>8.1f}MB"
    )
    print(
        f"{'Tốc độ':12}{latency_ms(fp32, inputs):>8.1f}ms{latency_ms(int8, inputs):>8.1f}ms"
    )
    print(f"{'Accuracy':12}{acc_fp32:>9.1f}%{acc_int8:>9.1f}%")
    print(f"Dự đoán giống nhau giữa FP32 và INT8: {agree:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="test.csv")
    parser.add_argument("--root", required=True, help="thư mục ảnh ISIC2019")
    parser.add_argument("--n", type=int, default=300, help="số ảnh để so sánh")
    args = parser.parse_args()

    samples = load_samples(args.csv, args.root, args.n)
    inputs = [preprocess_numpy(Image.open(path)) for path, _ in samples]
    class_names = [label for _, label in samples]

    compare("multiclass", inputs, np.array([CLASSES.index(c) for c in class_names]))
    compare("binary", inputs, np.array([int(c in MALIGNANT) for c in class_names]))
