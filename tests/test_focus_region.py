"""Polygon validation and crop tests without Flask/database or model inference."""

import pytest
from PIL import Image

from skin_cancer.webapp.services.focus_region import apply_focus_region, parse_polygon


def test_valid_normalized_triangle_can_crop_in_memory_image():
    points = parse_polygon({"points": [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]})
    assert len(points) == 3

    image = Image.new("RGB", (400, 400), color=(120, 80, 90))
    cropped = apply_focus_region(image, {"points": points})
    assert 0 < cropped.width < image.width
    assert 0 < cropped.height < image.height
    assert apply_focus_region(image, None) is image


@pytest.mark.parametrize("payload", ["invalid", ["not-an-object"], 123, True])
def test_non_object_json_is_a_validation_error(payload):
    with pytest.raises(ValueError):
        parse_polygon(payload)


@pytest.mark.parametrize(
    "invalid_point",
    [{"x": 0.2, "y": 0.2}, "02", [0.2], [0.2, 0.2, 0.2], [True, 0.2]],
)
def test_point_must_be_a_pair_of_numeric_coordinates(invalid_point):
    with pytest.raises(ValueError):
        parse_polygon({"points": [invalid_point, [0.8, 0.2], [0.5, 0.8]]})


def test_tiny_and_out_of_range_regions_are_rejected():
    with pytest.raises(ValueError):
        parse_polygon({"points": [[0.1, 0.1], [0.11, 0.1], [0.1, 0.11]]})
    with pytest.raises(ValueError):
        parse_polygon({"points": [[0.2, 0.2], [2.0, 0.2], [0.5, 0.8]]})
