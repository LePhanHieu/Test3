"""Keep existing AI uncertainty thresholds and output contract stable."""

from skin_cancer.webapp.services.uncertainty import check_uncertainty


def test_confident_eight_class_distribution():
    result = check_uncertainty([0.92, 0.04, 0.01, 0.01, 0.01, 0.005, 0.003, 0.002])
    assert set(result) == {"is_uncertain", "margin", "entropy", "message"}
    assert result["is_uncertain"] is False
    assert result["margin"] == 0.88
    assert result["message"] is None
    assert 0 <= result["entropy"] < 0.60


def test_near_tied_predictions_request_doctor_review():
    result = check_uncertainty([0.48, 0.44, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01])
    assert result["is_uncertain"] is True
    assert result["margin"] == 0.04
    assert result["message"] == "Ca này khó, nên hỏi bác sĩ."


def test_mapping_probabilities_match_list_probabilities():
    probabilities = {"MEL": 0.92, "NV": 0.04, "BCC": 0.04}
    assert check_uncertainty(probabilities) == check_uncertainty(list(probabilities.values()))


def test_uniform_distribution_has_maximum_normalized_entropy():
    result = check_uncertainty([0.125] * 8)
    assert result["is_uncertain"] is True
    assert result["entropy"] == 1.0


def test_one_hot_distribution_is_certain():
    result = check_uncertainty([1.0] + [0.0] * 7)
    assert result["is_uncertain"] is False
    assert result["entropy"] == 0.0
