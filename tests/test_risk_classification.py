"""Risk scoring and classification boundary tests (spec sections 18-19, 49)."""
import pytest


def test_risk_score_sums_distinct_categories_only(engine):
    weights = {"nic": 30, "salary": 20, "email": 10, "bank_account": 30}
    # NIC appears 18 times but must not multiply the score - distinct categories only
    counts = {"nic": 18, "salary": 1, "email": 12, "bank_account": 8}
    score = engine.scorer.calculate_risk(counts, weights)
    assert score == 90  # 30 + 20 + 10 + 30


def test_risk_score_capped_at_100(engine):
    weights = {"a": 40, "b": 40, "c": 40, "d": 40}
    counts = {"a": 1, "b": 1, "c": 1, "d": 1}
    score = engine.scorer.calculate_risk(counts, weights)
    assert score == 100


def test_risk_score_zero_with_no_detections(engine):
    score = engine.scorer.calculate_risk({}, {"nic": 30})
    assert score == 0


CLASSIFICATION_THRESHOLDS = [
    ("PUBLIC", 0, 20),
    ("INTERNAL", 21, 40),
    ("CONFIDENTIAL", 41, 70),
    ("RESTRICTED", 71, 100),
]


def _thresholds(engine):
    return [engine.classifier.ClassificationThreshold(c, mn, mx) for c, mn, mx in CLASSIFICATION_THRESHOLDS]


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "PUBLIC"),
        (20, "PUBLIC"),
        (21, "INTERNAL"),
        (40, "INTERNAL"),
        (41, "CONFIDENTIAL"),
        (70, "CONFIDENTIAL"),
        (71, "RESTRICTED"),
        (100, "RESTRICTED"),
    ],
)
def test_classification_boundaries(engine, score, expected):
    assert engine.classifier.classify(score, _thresholds(engine)) == expected


def test_classification_fails_closed_above_max(engine):
    assert engine.classifier.classify(150, _thresholds(engine)) == "RESTRICTED"
