"""Task 6: Chạy model bằng ONNX Runtime (thay cho PyTorch ở bước dự đoán)."""

from pathlib import Path
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None
from PIL import Image

# Giống hệt transforms.Normalize trong app.py
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)


def preprocess_numpy(pil_img):
    """PIL -> numpy (1, 3, 224, 224), tương đương preprocess của PyTorch."""
    img = pil_img.convert("RGB").resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0  # (H, W, 3), giá trị 0..1
    arr = arr.transpose(2, 0, 1)[None]  # (1, 3, H, W)
    return ((arr - MEAN) / STD).astype(np.float32)


def softmax(logits):
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


class OnnxPredictor:
    """Giữ 2 session ONNX: binary (lành/ác) và multiclass (8 loại)."""

    def __init__(self, ckpt_dir, suffix=""):
        if ort is None:
            raise RuntimeError("Thư viện 'onnxruntime' chưa được cài đặt. Chạy: pip install onnxruntime")
        # suffix = "" -> binary.onnx, multiclass.onnx (FP32)
        # suffix = "_int8" -> binary_int8.onnx, multiclass_int8.onnx
        ckpt_dir = Path(ckpt_dir)
        providers = ["CPUExecutionProvider"]
        self.binary = ort.InferenceSession(
            str(ckpt_dir / f"binary{suffix}.onnx"), providers=providers
        )
        self.multiclass = ort.InferenceSession(
            str(ckpt_dir / f"multiclass{suffix}.onnx"), providers=providers
        )

    def predict(self, x):
        """x: numpy float32 (1, 3, 224, 224).
        Trả về (xác suất ác tính, mảng xác suất 8 lớp)."""
        bin_logits = self.binary.run(None, {"input": x})[0]
        mc_logits = self.multiclass.run(None, {"input": x})[0]
        p_malig = float(softmax(bin_logits)[0, 1])
        probs_mc = softmax(mc_logits)[0]
        return p_malig, probs_mc
