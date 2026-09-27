import pytest
from pydantic import ValidationError

from app.schemas.api import ScoreWeights
from app.services.scoring import score_products


def test_default_weights_and_stable_ranking():
    weights = ScoreWeights().model_dump(exclude={"adjustment_reason"})
    products = [
        {"product_name": "B", "vendor_name": "V2", "price": 100, "performance_score": 80, "service_score": 80},
        {"product_name": "A", "vendor_name": "V1", "price": 100, "performance_score": 80, "service_score": 80},
    ]
    result = score_products(products, weights)
    assert [item["product_name"] for item in result] == ["A", "B"]
    assert result[0]["score_breakdown"]["price"] == 100


def test_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        ScoreWeights(price=0.5, performance=0.5, service=0.5)

