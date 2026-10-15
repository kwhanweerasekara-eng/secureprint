"""Runs the synthetic dataset (generate_dataset.py) through the real
extraction -> detection -> risk scoring -> classification engine and reports:

  - Detection precision / recall / F1 (category presence, micro-averaged)
  - Classification accuracy
  - False positive rate / false negative rate (category presence)
  - Average processing latency per document

This exercises the exact same engine modules the API uses
(services/document-analysis, services/classification) - not a re-implementation.

Usage:
    python tests/evaluation/run_evaluation.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
for d in ["document-analysis", "classification"]:
    sys.path.insert(0, str(REPO_ROOT / "services" / d))

import classifier  # noqa: E402
import detector  # noqa: E402
import extractor  # noqa: E402
import scorer  # noqa: E402

DATASET_DIR = REPO_ROOT / "tests" / "fixtures" / "synthetic"
REPORT_PATH = REPO_ROOT / "tests" / "evaluation" / "report.json"


def load_rules_and_config():
    patterns = json.loads((REPO_ROOT / "config" / "patterns.json").read_text())
    keywords = json.loads((REPO_ROOT / "config" / "keywords.json").read_text())
    weights_cfg = json.loads((REPO_ROOT / "config" / "weights.json").read_text())
    policies_cfg = json.loads((REPO_ROOT / "config" / "policies.json").read_text())

    rules = [
        detector.PatternRule(
            name=name,
            category=c["category"],
            pattern=c["pattern"],
            priority=c.get("priority", 50),
            requires_keyword_context=c.get("requires_keyword_context", False),
            context_keywords=c.get("context_keywords", []),
        )
        for name, c in patterns.items()
    ]
    weights = {cat: c["weight"] for cat, c in weights_cfg.items()}
    thresholds = [
        classifier.ClassificationThreshold(cls, c["min_score"], c["max_score"]) for cls, c in policies_cfg.items()
    ]
    return rules, keywords, weights, thresholds


def load_category_floors() -> dict[str, str]:
    """Minimum classification per category, from config/weights.json."""
    weights_cfg = json.loads((REPO_ROOT / "config" / "weights.json").read_text())
    return {cat: c["min_classification"] for cat, c in weights_cfg.items() if c.get("min_classification")}


def evaluate() -> dict:
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text())
    rules, keywords, weights, thresholds = load_rules_and_config()
    floors = load_category_floors()

    tp = fp = fn = 0
    classification_correct = 0
    latencies_ms = []
    per_doc_results = []

    for entry in manifest:
        pdf_path = DATASET_DIR / entry["filename"]
        started = time.perf_counter()

        extraction = extractor.extract_document(str(pdf_path))
        detections = detector.detect(extraction, rules, keywords)
        categories = detector.summarize_categories(detections)
        score = scorer.calculate_risk(categories, weights)
        predicted_classification = classifier.apply_floors(
            classifier.classify(score, thresholds), detector.value_categories(detections), floors)

        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(elapsed_ms)

        expected = set(entry["expected_categories"])
        predicted = set(categories.keys())

        doc_tp = len(expected & predicted)
        doc_fp = len(predicted - expected)
        doc_fn = len(expected - predicted)
        tp += doc_tp
        fp += doc_fp
        fn += doc_fn

        classification_match = predicted_classification == entry["expected_classification"]
        classification_correct += int(classification_match)

        per_doc_results.append(
            {
                "filename": entry["filename"],
                "scenario": entry["scenario"],
                "expected_categories": sorted(expected),
                "predicted_categories": sorted(predicted),
                "expected_classification": entry["expected_classification"],
                "predicted_classification": predicted_classification,
                "classification_correct": classification_match,
                "risk_score": score,
                "latency_ms": round(elapsed_ms, 3),
            }
        )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    false_positive_rate = fp / (tp + fp) if (tp + fp) else 0.0
    false_negative_rate = fn / (tp + fn) if (tp + fn) else 0.0
    classification_accuracy = classification_correct / len(manifest)

    report = {
        "dataset_size": len(manifest),
        "detection_precision": round(precision, 4),
        "detection_recall": round(recall, 4),
        "detection_f1": round(f1, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "false_negative_rate": round(false_negative_rate, 4),
        "classification_accuracy": round(classification_accuracy, 4),
        "average_latency_ms": round(statistics.mean(latencies_ms), 3),
        "p95_latency_ms": round(sorted(latencies_ms)[int(len(latencies_ms) * 0.95) - 1], 3),
        "per_document": per_doc_results,
    }
    return report


def main() -> None:
    if not DATASET_DIR.exists() or not (DATASET_DIR / "manifest.json").exists():
        print("Dataset not found. Run tests/evaluation/generate_dataset.py first.", file=sys.stderr)
        sys.exit(1)

    report = evaluate()
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(f"Documents evaluated:      {report['dataset_size']}")
    print(f"Detection precision:      {report['detection_precision']:.2%}")
    print(f"Detection recall:         {report['detection_recall']:.2%}")
    print(f"Detection F1:             {report['detection_f1']:.2%}")
    print(f"False positive rate:      {report['false_positive_rate']:.2%}")
    print(f"False negative rate:      {report['false_negative_rate']:.2%}")
    print(f"Classification accuracy:  {report['classification_accuracy']:.2%}")
    print(f"Average latency:          {report['average_latency_ms']:.2f} ms")
    print(f"P95 latency:              {report['p95_latency_ms']:.2f} ms")
    print(f"Full report written to:   {REPORT_PATH}")

    misclassified = [d for d in report["per_document"] if not d["classification_correct"]]
    if misclassified:
        print(f"\nMisclassified documents ({len(misclassified)}):")
        for d in misclassified:
            print(f"  {d['filename']}: expected {d['expected_classification']}, got {d['predicted_classification']} (score={d['risk_score']})")


if __name__ == "__main__":
    main()
