"""Synthetic-image tests; never load model weights or access real uploads."""

import cv2
import numpy as np
import pytest
from PIL import Image

from skin_cancer.webapp.services.image_quality import check_image_quality
from skin_cancer.webapp.services.measurement_service import MeasurementService
from skin_cancer.webapp.services.onnx_inference import preprocess_numpy, softmax


def test_opencv_measurement_rejects_missing_image_without_writing_overlay(tmp_path):
    overlay_folder = tmp_path / "contours"
    result = MeasurementService().measure(tmp_path / "missing.png", overlay_folder)
    assert result.status == "FAILED"
    assert result.error_code == "IMAGE_READ_ERROR"
    assert not overlay_folder.exists()


def test_opencv_measurement_detects_synthetic_lesion_and_writes_overlay_in_tmp(tmp_path):
    image = np.full((400, 400, 3), 210, dtype=np.uint8)
    cv2.circle(image, (200, 200), 75, (35, 35, 35), -1)
    source = tmp_path / "lesion.png"
    assert cv2.imwrite(str(source), image)
    output = tmp_path / "contours"
    result = MeasurementService().measure(source, output)

    assert result.status == "COMPLETED", result
    assert result.lesion_area_px > 10000
    assert 0 < result.lesion_ratio < 0.90
    assert result.lesion_perimeter_px > 0
    assert result.bbox_width > 0 and result.bbox_height > 0
    assert result.contour_path is not None
    assert (output / (result.contour_path.split("/")[-1])).is_file()


def test_image_quality_reports_small_dark_blurry_images():
    result = check_image_quality(Image.new("RGB", (64, 64), color=(1, 1, 1)))
    assert result["ok"] is False
    assert result["metrics"]["width"] == 64
    assert result["metrics"]["height"] == 64
    assert len(result["warnings"]) >= 3


def test_onnx_preprocessing_produces_expected_shape_dtype_and_normalization():
    image = Image.new("RGB", (224, 224), color=(255, 0, 0))
    output = preprocess_numpy(image)
    assert output.shape == (1, 3, 224, 224)
    assert output.dtype == np.float32
    np.testing.assert_allclose(output[0, :, 0, 0], [(1 - 0.485) / 0.229, -0.456 / 0.224, -0.406 / 0.225])


def test_softmax_probabilities_are_stable_and_sum_to_one():
    logits = np.array([[1000.0, 999.0, 998.0], [-1000.0, -1001.0, -999.0]], dtype=np.float32)
    probabilities = softmax(logits)
    assert np.isfinite(probabilities).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), [1.0, 1.0], atol=1e-6)
    assert probabilities[0, 0] > probabilities[0, 1] > probabilities[0, 2]


@pytest.mark.parametrize("shape", [(256, 256), (224, 224), (512, 512)])
def test_onnx_preprocessing_accepts_varied_source_sizes(shape):
    output = preprocess_numpy(Image.new("RGB", shape, color=(120, 80, 60)))
    assert output.shape == (1, 3, 224, 224)
