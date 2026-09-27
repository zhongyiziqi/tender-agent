from __future__ import annotations

from typing import Any


def score_products(products: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    eligible_prices = [
        float(item["price"])
        for item in products
        if item.get("meets_required", True) and item.get("price")
    ]
    minimum_price = min(eligible_prices) if eligible_prices else None
    scored: list[dict[str, Any]] = []
    for product in products:
        if not product.get("meets_required", True):
            continue
        price = product.get("price")
        price_score = (minimum_price / float(price) * 100) if minimum_price and price else 0.0
        performance_score = float(product.get("performance_score", 0))
        service_score = float(product.get("service_score", 0))
        total = (
            price_score * weights["price"]
            + performance_score * weights["performance"]
            + service_score * weights["service"]
        )
        scored.append(
            {
                **product,
                "score_breakdown": {
                    "price": round(price_score, 2),
                    "performance": round(performance_score, 2),
                    "service": round(service_score, 2),
                },
                "total_score": round(total, 2),
            }
        )
    scored.sort(key=lambda item: (-item["total_score"], item["product_name"], item["vendor_name"]))
    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank
    return scored

