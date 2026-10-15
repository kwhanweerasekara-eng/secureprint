"""Evaluates the engine on the realistic corpus (corpus.py) at three levels:

  1. Values: is each annotated sensitive value found by a pattern, and how
     many pattern matches are not sensitive at all (precision / recall)?
  2. Categories: the same at document level, including keyword hits, which
     is what drives the risk score.
  3. Masking: after "Mask and print", can any annotated value still be read
     from the output PDF? This is the measure that matters on paper.

Classification accuracy is reported against the author's provisional labels,
and against the reviewers' majority once reviewer_labels.csv is filled in
(see calibrate_thresholds.py). Latency is measured per document for analysis
alone and for analysis plus masking, watermark and footer.

Usage:
    python tests/evaluation/realistic/corpus.py        # once, builds the PDFs
    python tests/evaluation/realistic/run_realistic.py
    python tests/evaluation/realistic/run_realistic.py holdout   # after corpus.py holdout
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE.parent))
for d in ["document-analysis", "classification", "document-processing"]:
    sys.path.insert(0, str(REPO_ROOT / "services" / d))

import fitz  # noqa: E402
import classifier  # noqa: E402
import detector  # noqa: E402
import extractor  # noqa: E402
import processor  # noqa: E402
import scorer  # noqa: E402
from run_evaluation import load_category_floors, load_rules_and_config  # noqa: E402

FLOORS = load_category_floors()

HOLDOUT = len(sys.argv) > 1 and sys.argv[1] == "holdout"
DATASET_DIR = REPO_ROOT / "tests" / "fixtures" / ("realistic-holdout" if HOLDOUT else "realistic")
REPORT_PATH = HERE / ("report-holdout.json" if HOLDOUT else "report.json")
LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
MASKABLE = {"nic", "card", "bank_account", "iban", "credential", "api_key", "passport", "salary",
            "employee_id", "email", "telephone"}
MIN_LEAK_CHECK_LEN = 5  # shorter values (a CVV) also occur by chance elsewhere on the page


def norm(text: str) -> str:
    return re.sub(r"[\s\-/]", "", text).lower()


def overlaps(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a in b or (len(b) >= 4 and b in a)


def analyse(path: Path, rules, keywords, weights, thresholds):
    started = time.perf_counter()
    extraction = extractor.extract_document(str(path))
    detections = detector.detect(extraction, rules, keywords)
    categories = detector.summarize_categories(detections)
    score = scorer.calculate_risk(categories, weights)
    level = classifier.apply_floors(classifier.classify(score, thresholds), detector.value_categories(detections), FLOORS)
    return extraction, detections, categories, score, level, (time.perf_counter() - started) * 1000


def mask(path: Path, detections, out_path: Path) -> float:
    started = time.perf_counter()
    targets = []
    for d in detections:
        for b in (d.bboxes or ([d.bbox] if d.bbox else [])):
            targets.append({"page": d.page, "bbox": list(b)})
    options = processor.SanitizeOptions(require_masking=True, require_watermark=True, require_footer=True,
                                        footer_text="RESTRICTED | Evaluation run")
    processor.sanitize_document(str(path), str(out_path), targets, options)
    return (time.perf_counter() - started) * 1000


HUMAN_COLUMNS = ["reviewer_1", "reviewer_2", "reviewer_3"]
SIMULATED_COLUMNS = ["user_1_simulated", "user_2_simulated", "user_3_simulated"]


def read_reviewer_sheet(path: Path) -> tuple[dict[str, list[str]], bool]:
    """Returns ({filename: [three labels]}, simulated). Rows without three
    valid labels are skipped. `simulated` is True when the sheet holds the
    simulated reviewers (User 1-3) rather than real people."""
    import csv

    if not path.exists():
        return {}, False
    labels: dict[str, list[str]] = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        simulated = SIMULATED_COLUMNS[0] in (reader.fieldnames or [])
        columns = SIMULATED_COLUMNS if simulated else HUMAN_COLUMNS
        for row in reader:
            values = [row.get(c, "").strip().upper() for c in columns]
            if all(v in LEVELS for v in values):
                labels[row["filename"]] = values
    return labels, simulated


def majority(values: list[str]) -> str:
    top = max(set(values), key=values.count)
    # With no majority (three different labels) take the middle level.
    return top if values.count(top) >= 2 else sorted(values, key=LEVELS.index)[1]


def reviewer_sheet_path(holdout: bool = HOLDOUT) -> Path:
    return HERE / ("reviewer_labels-holdout.csv" if holdout else "reviewer_labels.csv")


def load_reviewer_majority() -> tuple[dict[str, str], bool]:
    labels, simulated = read_reviewer_sheet(reviewer_sheet_path())
    return {name: majority(values) for name, values in labels.items()}, simulated


def confusion(pairs: list[tuple[str, str]]) -> dict:
    return {exp: {pred: sum(1 for e, p in pairs if e == exp and p == pred) for pred in LEVELS} for exp in LEVELS}


def evaluate() -> dict:
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text())
    rules, keywords, weights, thresholds = load_rules_and_config()
    reviewers, simulated_reviewers = load_reviewer_majority()

    v_tp = v_fn = v_fp = 0
    v_by_cat: dict[str, dict[str, int]] = {}
    c_tp = c_fp = c_fn = 0
    c_fp_by_cat: dict[str, int] = {}
    c_fn_by_cat: dict[str, int] = {}
    leak_checked = leaked = 0
    leak_by_cat: dict[str, dict[str, int]] = {}
    analysis_ms, total_ms = [], []
    provisional_pairs, reviewer_pairs = [], []
    per_doc = []

    with tempfile.TemporaryDirectory() as tmp:
        for entry in manifest:
            path = DATASET_DIR / entry["filename"]
            extraction, detections, categories, score, level, a_ms = analyse(path, rules, keywords, weights, thresholds)
            regex_hits = [d for d in detections if d.source == "regex"]
            truth = [t for t in entry["values"] if t["category"] in MASKABLE]

            # 1. values
            missed = []
            for t in truth:
                stats = v_by_cat.setdefault(t["category"], {"found": 0, "missed": 0})
                if any(d.page == t["page"] and overlaps(t["value"], d.value) for d in regex_hits):
                    v_tp += 1
                    stats["found"] += 1
                else:
                    v_fn += 1
                    stats["missed"] += 1
                    missed.append(f"{t['category']}: {t['value']}")
            false_hits = [d for d in regex_hits
                          if not any(d.page == t["page"] and overlaps(t["value"], d.value) for t in entry["values"])]
            v_fp += len(false_hits)

            # 2. categories
            expected = set(entry["expected_categories"])
            predicted = set(categories)
            c_tp += len(expected & predicted)
            c_fp += len(predicted - expected)
            c_fn += len(expected - predicted)
            for c in predicted - expected:
                c_fp_by_cat[c] = c_fp_by_cat.get(c, 0) + 1
            for c in expected - predicted:
                c_fn_by_cat[c] = c_fn_by_cat.get(c, 0) + 1

            # 3. masking
            out_path = Path(tmp) / entry["filename"]
            m_ms = mask(path, detections, out_path)
            with fitz.open(str(out_path)) as out:
                text = "\n".join(p.get_text() for p in out)
            flat = norm(text)
            doc_leaks = []
            for t in truth:
                if len(norm(t["value"])) < MIN_LEAK_CHECK_LEN:
                    continue
                leak_checked += 1
                stats = leak_by_cat.setdefault(t["category"], {"checked": 0, "leaked": 0})
                stats["checked"] += 1
                if t["value"] in text or norm(t["value"]) in flat:
                    leaked += 1
                    stats["leaked"] += 1
                    doc_leaks.append(f"{t['category']}: {t['value']}")

            analysis_ms.append(a_ms)
            total_ms.append(a_ms + m_ms)
            provisional_pairs.append((entry["provisional_classification"], level))
            if entry["filename"] in reviewers:
                reviewer_pairs.append((reviewers[entry["filename"]], level))

            per_doc.append({
                "filename": entry["filename"],
                "doc_type": entry["doc_type"],
                "pages": extraction.page_count,
                "provisional_classification": entry["provisional_classification"],
                "reviewer_majority": reviewers.get(entry["filename"]),
                "predicted_classification": level,
                "risk_score": score,
                "expected_categories": sorted(expected),
                "predicted_categories": sorted(predicted),
                "missed_values": missed,
                "false_detections": [f"{d.category}: {d.value}" for d in false_hits],
                "leaked_after_masking": doc_leaks,
                "analysis_ms": round(a_ms, 2),
                "analysis_and_masking_ms": round(a_ms + m_ms, 2),
            })

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        return round(p, 4), round(r, 4), round(2 * p * r / (p + r), 4) if p + r else 0.0

    vp, vr, vf = prf(v_tp, v_fp, v_fn)
    cp, cr, cf = prf(c_tp, c_fp, c_fn)
    report = {
        "dataset_size": len(manifest),
        "annotated_values": v_tp + v_fn,
        "value_precision": vp, "value_recall": vr, "value_f1": vf,
        "value_false_detections": v_fp,
        "value_recall_by_category": {c: round(s["found"] / (s["found"] + s["missed"]), 4) for c, s in sorted(v_by_cat.items())},
        "category_precision": cp, "category_recall": cr, "category_f1": cf,
        "category_false_positives_by_category": dict(sorted(c_fp_by_cat.items(), key=lambda x: -x[1])),
        "category_misses_by_category": dict(sorted(c_fn_by_cat.items(), key=lambda x: -x[1])),
        "masking_values_checked": leak_checked,
        "masking_values_leaked": leaked,
        "masking_leak_rate": round(leaked / leak_checked, 4) if leak_checked else 0.0,
        "masking_leaks_by_category": {c: s for c, s in sorted(leak_by_cat.items()) if s["leaked"]},
        "classification_accuracy_vs_provisional": round(sum(e == p for e, p in provisional_pairs) / len(provisional_pairs), 4),
        "confusion_vs_provisional": confusion(provisional_pairs),
        "reviewer_labelled_documents": len(reviewer_pairs),
        "reviewers_simulated": simulated_reviewers,
        "classification_accuracy_vs_reviewers": (
            round(sum(e == p for e, p in reviewer_pairs) / len(reviewer_pairs), 4) if reviewer_pairs else None),
        "confusion_vs_reviewers": confusion(reviewer_pairs) if reviewer_pairs else None,
        "analysis_ms_mean": round(statistics.mean(analysis_ms), 2),
        "analysis_and_masking_ms_mean": round(statistics.mean(total_ms), 2),
        "analysis_and_masking_ms_max": round(max(total_ms), 2),
        "per_document": per_doc,
    }
    return report


def print_matrix(title: str, matrix: dict) -> None:
    print(f"\n{title} (rows = expected, columns = engine)")
    print(" " * 14 + "".join(f"{l[:4]:>7}" for l in LEVELS))
    for exp in LEVELS:
        print(f"{exp:<14}" + "".join(f"{matrix[exp][p]:>7}" for p in LEVELS))


def main() -> None:
    if not (DATASET_DIR / "manifest.json").exists():
        print("Corpus not found. Run tests/evaluation/realistic/corpus.py first.", file=sys.stderr)
        sys.exit(1)
    r = evaluate()
    REPORT_PATH.write_text(json.dumps(r, indent=2))

    print(f"Documents: {r['dataset_size']}   annotated sensitive values: {r['annotated_values']}")
    print(f"\nValue level      precision {r['value_precision']:.1%}  recall {r['value_recall']:.1%}  "
          f"F1 {r['value_f1']:.1%}  ({r['value_false_detections']} false detections)")
    print("  recall by category: " + ", ".join(f"{c} {x:.0%}" for c, x in r["value_recall_by_category"].items()))
    print(f"Category level   precision {r['category_precision']:.1%}  recall {r['category_recall']:.1%}  "
          f"F1 {r['category_f1']:.1%}")
    print(f"  false positives: {r['category_false_positives_by_category']}")
    print(f"  misses:          {r['category_misses_by_category']}")
    print(f"Masking          {r['masking_values_leaked']} of {r['masking_values_checked']} values still readable "
          f"after masking ({r['masking_leak_rate']:.1%})")
    print(f"Classification   {r['classification_accuracy_vs_provisional']:.1%} agreement with provisional labels")
    print_matrix("Confusion vs provisional labels", r["confusion_vs_provisional"])
    if r["confusion_vs_reviewers"]:
        who = "SIMULATED reviewers (User 1-3)" if r["reviewers_simulated"] else "reviewer majority"
        print(f"\nClassification   {r['classification_accuracy_vs_reviewers']:.1%} agreement with {who} "
              f"({r['reviewer_labelled_documents']} documents)")
        print_matrix(f"Confusion vs {who}", r["confusion_vs_reviewers"])
    print(f"\nLatency          analysis {r['analysis_ms_mean']:.1f} ms mean; with masking "
          f"{r['analysis_and_masking_ms_mean']:.1f} ms mean, {r['analysis_and_masking_ms_max']:.1f} ms max")
    print(f"Full report:     {REPORT_PATH}")


if __name__ == "__main__":
    main()
