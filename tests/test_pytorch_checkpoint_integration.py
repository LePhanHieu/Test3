"""Optional CPU-only smoke tests against real, unmodified EfficientNet-B0 checkpoints."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from skin_cancer.webapp.services.onnx_inference import OnnxPredictor, preprocess_numpy

CHECKPOINTS = Path(__file__).resolve().parents[1] / "skin_cancer" / "checkpoints"


@pytest.fixture(scope="module")
def actual_models():
    torch = pytest.importorskip("torch")
    timm = pytest.importorskip("timm")
    if not all((CHECKPOINTS / name).is_file() for name in ("best_binary.pth", "best_multiclass.pth")):
        pytest.skip("PyTorch checkpoints are absent")

    class SkinCancerEfficientNet(torch.nn.Module):
        def __init__(self, classes, dropout):
            super().__init__()
            self.backbone = timm.create_model("efficientnet_b0", pretrained=False, num_classes=0)
            self.head = torch.nn.Sequential(
                torch.nn.Dropout(dropout),
                torch.nn.Linear(self.backbone.num_features, 256),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(256, classes),
            )

        def forward(self, x):
            return self.head(self.backbone(x))

    binary = SkinCancerEfficientNet(2, 0.3)
    multi = SkinCancerEfficientNet(8, 0.4)
    binary.load_state_dict(torch.load(CHECKPOINTS / "best_binary.pth", map_location="cpu", weights_only=True))
    multi.load_state_dict(torch.load(CHECKPOINTS / "best_multiclass.pth", map_location="cpu", weights_only=True))
    binary.eval()
    multi.eval()
    return binary, multi


def _input():
    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    image = Image.new("RGB", (224, 224), color=(120, 80, 70))
    return (
        torchvision.transforms.Compose(
            [
                torchvision.transforms.ToTensor(),
                torchvision.transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )(image)
        .unsqueeze(0)
        .to(dtype=torch.float32)
    )


def test_real_pytorch_binary_and_multiclass_checkpoints_produce_probabilities(actual_models):
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1)
    with torch.no_grad():
        binary = torch.softmax(actual_models[0](_input()), dim=1)
        multiclass = torch.softmax(actual_models[1](_input()), dim=1)
    assert binary.shape == (1, 2)
    assert multiclass.shape == (1, 8)
    for probabilities in (binary, multiclass):
        assert torch.isfinite(probabilities).all()
        assert torch.all((probabilities >= 0) & (probabilities <= 1))
        assert float(probabilities.sum()) == pytest.approx(1.0, abs=1e-5)


def test_real_gradcam_produces_finite_heatmap(actual_models):
    torch = pytest.importorskip("torch")
    pytest.importorskip("pytorch_grad_cam")
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

    torch.set_num_threads(1)
    model = actual_models[1]
    with torch.no_grad():
        target_class = int(model(_input()).argmax(dim=1).item())
    with GradCAM(model=model, target_layers=[model.backbone.conv_head]) as cam:
        heatmap = cam(input_tensor=_input(), targets=[ClassifierOutputTarget(target_class)])[0]
    assert heatmap.shape == (224, 224)
    assert np.isfinite(heatmap).all()
    assert np.all((heatmap >= 0) & (heatmap <= 1))


def test_fp32_onnx_and_pytorch_checkpoints_agree_on_synthetic_image(actual_models):
    torch = pytest.importorskip("torch")
    pytest.importorskip("onnxruntime")
    torch.set_num_threads(1)
    with torch.no_grad():
        binary = torch.softmax(actual_models[0](_input()), dim=1)[0, 1].item()
        multiclass = torch.softmax(actual_models[1](_input()), dim=1)[0].numpy()

    onnx = OnnxPredictor(CHECKPOINTS)
    image = Image.new("RGB", (224, 224), color=(120, 80, 70))
    onnx_binary, onnx_multiclass = onnx.predict(preprocess_numpy(image))
    assert onnx_binary == pytest.approx(binary, abs=1e-3)
    np.testing.assert_allclose(onnx_multiclass, multiclass, atol=1e-3)
