"""Task 6: Chuyển 2 model PyTorch (.pth) sang ONNX.

Chạy từ thư mục gốc project:
    python -m skin_cancer.webapp.scripts.export_onnx
Cần: pip install onnx onnxruntime
"""

import numpy as np
import onnxruntime as ort
import timm
import torch
import torch.nn as nn

from skin_cancer.webapp.scripts.common import CKPT_DIR


# Phải giống hệt class trong app.py
class SkinCancerEfficientNet(nn.Module):
    def __init__(self, backbone="efficientnet_b0", num_classes=2, dropout=0.3):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=False, num_classes=0)
        feat_dim = self.backbone.num_features
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(feat_dim, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        return self.head(self.backbone(x))


def export(name, num_classes, dropout):
    model = SkinCancerEfficientNet(num_classes=num_classes, dropout=dropout)
    model.load_state_dict(torch.load(CKPT_DIR / f"best_{name}.pth", map_location="cpu"))
    model.eval()

    onnx_path = CKPT_DIR / f"{name}.onnx"
    dummy = torch.randn(1, 3, 224, 224)
    kwargs = dict(
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={
            "input": {0: "batch"},
            "logits": {0: "batch"},
        },  # batch size tuỳ ý
        opset_version=17,
    )
    try:
        # torch mới: dùng exporter cũ cho ổn định
        torch.onnx.export(model, dummy, str(onnx_path), dynamo=False, **kwargs)
    except TypeError:
        # torch cũ không có tham số dynamo
        torch.onnx.export(model, dummy, str(onnx_path), **kwargs)

    # Kiểm tra: ONNX phải cho kết quả gần giống PyTorch
    x = torch.randn(4, 3, 224, 224)
    with torch.no_grad():
        expected = model(x).numpy()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"input": x.numpy()})[0]
    diff = float(np.abs(expected - actual).max())
    print(
        f"[{name}] đã lưu {onnx_path.name}, sai khác lớn nhất so với PyTorch: {diff:.6f}"
    )
    assert diff < 1e-3, "ONNX lệch quá nhiều so với PyTorch, hãy kiểm tra lại!"


if __name__ == "__main__":
    try:
        timm.layers.set_exportable(True)  # giúp timm xuất ONNX ổn định hơn
    except AttributeError:
        pass
    export("binary", num_classes=2, dropout=0.3)
    export("multiclass", num_classes=8, dropout=0.4)
