"""Task 5: Quantization INT8 cho 2 model ONNX (post-training static quantization).

Chạy từ thư mục gốc project:
    python -m skin_cancer.webapp.scripts.quantize_int8 --csv skin_cancer/train.csv --root /duong/dan/isic2019
Cần chạy export_onnx trước. Dùng ảnh TRAIN để calibration (không dùng ảnh test).
"""

import argparse

from onnxruntime.quantization import (
    CalibrationDataReader,
    QuantFormat,
    QuantType,
    quantize_static,
)
from PIL import Image

from skin_cancer.webapp.scripts.common import CKPT_DIR, load_samples
from skin_cancer.webapp.services.onnx_inference import preprocess_numpy


class ImageReader(CalibrationDataReader):
    """Đưa lần lượt từng ảnh mẫu cho ONNX Runtime để nó đo dải giá trị."""

    def __init__(self, samples):
        batches = [{"input": preprocess_numpy(Image.open(path))} for path, _ in samples]
        self.data = iter(batches)

    def get_next(self):
        return next(self.data, None)


def quantize(name, samples):
    src = CKPT_DIR / f"{name}.onnx"
    dst = CKPT_DIR / f"{name}_int8.onnx"
    quantize_static(
        str(src),
        str(dst),
        ImageReader(samples),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        op_types_to_quantize=["Conv", "Gemm", "MatMul"],  # chỉ lượng tử hoá lớp nặng
    )
    before = src.stat().st_size / 1e6
    after = dst.stat().st_size / 1e6
    print(
        f"[{name}] {before:.1f} MB -> {after:.1f} MB (nhỏ hơn {before / after:.1f} lần)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="train.csv")
    parser.add_argument(
        "--root",
        required=True,
        help="thư mục chứa ảnh ISIC2019 (có thư mục con MEL, NV, ...)",
    )
    parser.add_argument("--n", type=int, default=200, help="số ảnh calibration")
    args = parser.parse_args()

    samples = load_samples(args.csv, args.root, args.n)
    quantize("binary", samples)
    quantize("multiclass", samples)
