from src.score.service import normalize_weights


def test_weights_sum_to_one() -> None:
    result = normalize_weights({"power": 0.5, "heat_offtake": 0.5, "climate": 0.5, "connectivity": 0.5, "commercial": 0.5})
    assert round(sum(result.values()), 6) == 1.0


def test_negative_weights_are_clipped() -> None:
    result = normalize_weights({"power": -1.0, "heat_offtake": 1.0, "climate": 0.0, "connectivity": 0.0, "commercial": 0.0})
    assert result["power"] == 0.0
