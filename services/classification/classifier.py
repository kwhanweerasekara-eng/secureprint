"""Maps a risk score onto a security classification using configurable
thresholds. Fails closed: a score above every configured range is treated as
the most severe configured classification rather than silently passing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassificationThreshold:
    classification: str
    min_score: int
    max_score: int


def classify(score: int, thresholds: list[ClassificationThreshold]) -> str:
    ordered = sorted(thresholds, key=lambda t: t.min_score)
    for t in ordered:
        if t.min_score <= score <= t.max_score:
            return t.classification
    if ordered and score > ordered[-1].max_score:
        return ordered[-1].classification
    if ordered and score < ordered[0].min_score:
        return ordered[0].classification
    return "RESTRICTED"


LEVEL_ORDER = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]


def apply_floors(classification: str, value_categories: set[str], floors: dict[str, str]) -> str:
    """Raises the classification to the minimum level some categories demand
    on their own, whatever the score. A real password, API key or card number
    makes a page Restricted (proposal Table 3.1 and test case T05), even
    though one such value alone scores only 40-45. Only categories backed by
    an actual detected value count, not the bare word "password"."""
    level = classification
    for category in value_categories:
        floor = floors.get(category)
        if floor in LEVEL_ORDER and LEVEL_ORDER.index(floor) > LEVEL_ORDER.index(level):
            level = floor
    return level
