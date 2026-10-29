"""Optional real-checkpoint smoke tests; no PyTorch model or external services."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from skin_cancer.webapp.services.onnx_inference import OnnxPredictor, preprocess_numpy

CHECKPOINTS = Path(__file__).resolve().parents[1] / "skin_cancer" / "checkpoints"


@pytest.mark.parametrize("suffix", ["", "_int8"])
def test_real_onnx_checkpoint_loads_and_produces_normalized_probabilities(suffix):
    pytest.importorskip("onnxruntime")
    if not all((CHECKPOINTS / f"{model}{suffix}.onnx").is_file() for model in ("binary", "multiclass")):
        pytest.skip("ONNX checkpoint is absent")

    predictor = OnnxPredictor(CHECKPOINTS, suffix=suffix)
    image = Image.new("RGB", (320, 280), color=(120, 80, 70))
    probability, multiclass = predictor.predict(preprocess_numpy(image))

    assert 0 <= probability <= 1
    assert multiclass.ndim == 1
    assert len(multiclass) >= 2
    assert np.isfinite(multiclass).all()
    assert np.all((multiclass >= 0) & (multiclass <= 1))
    assert float(multiclass.sum()) == pytest.approx(1, abs=1e-5)
