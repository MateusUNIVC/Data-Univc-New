from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def distribution(rows: Iterable[dict]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    numeric: dict[str, float | None] = {}

    for row in rows:
        label = row["option_label"]
        counts[label] += int(row["response_count"])
        numeric[label] = row.get("numeric_value")

    total = sum(counts.values())
    items = []
    for label, count in counts.items():
        items.append(
            {
                "label": label,
                "count": count,
                "percentage": (count / total * 100.0) if total else 0.0,
                "numeric_value": numeric.get(label),
            }
        )

    return {"total": total, "items": items}


def weighted_mean(items: Iterable[dict]) -> float | None:
    numerator = 0.0
    denominator = 0
    for item in items:
        value = item.get("numeric_value")
        count = int(item.get("count", 0))
        if value is None:
            continue
        numerator += float(value) * count
        denominator += count
    if denominator == 0:
        return None
    return numerator / denominator


def nps_score(items: Iterable[dict]) -> dict:
    promoters = 0
    passives = 0
    detractors = 0

    for item in items:
        value = item.get("numeric_value")
        count = int(item.get("count", 0))
        if value is None:
            continue
        value = float(value)
        if value >= 9:
            promoters += count
        elif value >= 7:
            passives += count
        else:
            detractors += count

    total = promoters + passives + detractors
    if total == 0:
        return {
            "score": None,
            "promoters": 0,
            "passives": 0,
            "detractors": 0,
            "total": 0,
        }

    score = (promoters / total * 100.0) - (detractors / total * 100.0)
    return {
        "score": score,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "total": total,
    }


def metric_summary(metric_type: str, dist: dict) -> dict:
    items = dist["items"]
    if metric_type == "nps":
        result = nps_score(items)
        result["type"] = "nps"
        return result
    if metric_type == "numeric":
        return {
            "type": "numeric",
            "mean": weighted_mean(items),
            "total": dist["total"],
        }
    if metric_type == "text":
        return {
            "type": "text",
            "total": dist["total"],
            "top_option": max(items, key=lambda item: item["count"], default=None),
        }
    return {
        "type": "categorical",
        "total": dist["total"],
        "top_option": max(items, key=lambda item: item["count"], default=None),
    }
