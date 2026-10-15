"""Risk scoring. Score is the sum of the configured weight for each DISTINCT
sensitive category present in the document, capped at 100. Occurrence counts
are recorded for display but never multiply the score."""
from __future__ import annotations

MAX_SCORE = 100


def calculate_risk(category_counts: dict[str, int], weights: dict[str, int]) -> int:
    score = 0
    for category, count in category_counts.items():
        if count > 0:
            score += weights.get(category, 0)
    return min(score, MAX_SCORE)
