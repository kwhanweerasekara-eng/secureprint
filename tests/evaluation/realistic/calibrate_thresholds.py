"""Human-reviewer calibration of the classification thresholds (proposal 3.5).

Step 1 - make the labelling sheet (does not overwrite an existing one):
    python tests/evaluation/realistic/calibrate_thresholds.py sheet

Three reviewers each open the PDFs in tests/fixtures/realistic/ and, working
independently, write PUBLIC, INTERNAL, CONFIDENTIAL or RESTRICTED in their own
column of reviewer_labels.csv, following REVIEWER_GUIDE.md.

Step 2 - calibrate once every row has three labels:
    python tests/evaluation/realistic/calibrate_thresholds.py calibrate

This reports how far the reviewers agree with each other (Fleiss' kappa),
how often the engine agrees with their majority at the current thresholds,
and the thresholds that maximise that agreement. Because the same documents
are used to choose the thresholds, it also reports a 5-fold cross-validated
accuracy, which is the honest figure to quote in the dissertation.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_realistic import (  # noqa: E402
    DATASET_DIR, HUMAN_COLUMNS, LEVELS, analyse, load_rules_and_config, majority, read_reviewer_sheet,
)

SHEET = HERE / "reviewer_labels.csv"
HOLDOUT_SHEET = HERE / "reviewer_labels-holdout.csv"
HOLDOUT_DIR = DATASET_DIR.parent / "realistic-holdout"


def make_sheet() -> None:
    if SHEET.exists():
        print(f"{SHEET.name} already exists - not overwriting it.")
        return
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text())
    with SHEET.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "title"] + HUMAN_COLUMNS)
        for m in manifest:
            w.writerow([m["filename"], m["title"], "", "", ""])
    print(f"Wrote {SHEET} with {len(manifest)} rows. Give each reviewer one column.")


def read_labels(path: Path = SHEET) -> tuple[dict[str, list[str]], bool]:
    labels, simulated = read_reviewer_sheet(path)
    if not labels:
        print(f"{path.name} has no fully labelled rows yet. Use one of: {', '.join(LEVELS)}.", file=sys.stderr)
        sys.exit(1)
    return labels, simulated


def fleiss_kappa(rows: list[list[str]]) -> float:
    n = len(rows[0])
    counts = [[r.count(level) for level in LEVELS] for r in rows]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(rows)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(LEVELS))]
    p_e = sum(p * p for p in p_j)
    return (p_bar - p_e) / (1 - p_e) if p_e < 1 else 1.0


def level_for(score: int, cuts: tuple[int, int, int], floor: str = LEVELS[0]) -> str:
    level = LEVELS[-1]
    for candidate, upper in zip(LEVELS, cuts):
        if score <= upper:
            level = candidate
            break
    return max(level, floor, key=LEVELS.index)


def accuracy(items: list[tuple], cuts) -> float:
    return sum(level_for(s, cuts, floor) == truth for s, truth, floor in items) / len(items)


def best_cuts(items: list[tuple[int, str]], current: tuple[int, int, int]):
    # Agreement only changes at observed scores, so only cut there (or at the
    # current values, which wins ties).
    scores = {s for s, *_ in items}
    candidates = sorted({c for c in scores | {s - 1 for s in scores} | set(current) if 0 <= c <= 99})
    best, best_key = current, None
    for cuts in combinations(candidates, 3):
        acc = accuracy(items, cuts)
        distance = sum(abs(a - b) for a, b in zip(cuts, current))
        key = (acc, -distance)  # prefer thresholds closest to the proposal's on ties
        if best_key is None or key > best_key:
            best, best_key = cuts, key
    return best, best_key[0]


def scored(labels: dict[str, list[str]], dataset: Path, rules, keywords, weights, thresholds):
    """(score, reviewer majority, minimum level the found categories demand)."""
    import classifier
    import detector
    from run_realistic import FLOORS

    items = []
    for filename, values in labels.items():
        _ex, detections, _cats, score, _level, _ms = analyse(dataset / filename, rules, keywords, weights, thresholds)
        floor = classifier.apply_floors(LEVELS[0], detector.value_categories(detections), FLOORS)
        items.append((score, majority(values), floor))
    return items


def calibrate() -> None:
    labels, simulated = read_labels()
    if simulated:
        print("NOTE: these labels come from SIMULATED reviewers (User 1-3), not real people.\n"
              "      Say so wherever the results are reported.\n")
    rules, keywords, weights, thresholds = load_rules_and_config()
    current = tuple(sorted(t.max_score for t in thresholds)[:3])
    items = scored(labels, DATASET_DIR, rules, keywords, weights, thresholds)

    kappa = fleiss_kappa(list(labels.values()))
    unanimous = sum(len(set(v)) == 1 for v in labels.values())
    print(f"Documents: {len(items)}   unanimous: {unanimous}   Fleiss' kappa: {kappa:.3f}")

    now = accuracy(items, current)
    cuts, fitted = best_cuts(items, current)
    print(f"Current thresholds {current}: engine agrees with the reviewer majority on {now:.1%}")
    print(f"Best thresholds    {cuts}: {fitted:.1%} on the same documents")

    rng = random.Random(7)
    shuffled = items[:]
    rng.shuffle(shuffled)
    folds = [shuffled[i::5] for i in range(5)]
    correct = 0
    for i, test in enumerate(folds):
        train = [x for j, f in enumerate(folds) if j != i for x in f]
        fold_cuts, _ = best_cuts(train, current)
        correct += sum(level_for(s, fold_cuts, fl) == t for s, t, fl in test)
    print(f"5-fold cross-validated accuracy with fitted thresholds: {correct / len(items):.1%}")

    holdout_labels, _ = read_reviewer_sheet(HOLDOUT_SHEET)
    if holdout_labels and (HOLDOUT_DIR / "manifest.json").exists():
        held = scored(holdout_labels, HOLDOUT_DIR, rules, keywords, weights, thresholds)
        print(f"Hold-out corpus ({len(held)} documents, not used for fitting): "
              f"current {accuracy(held, current):.1%}, fitted {accuracy(held, cuts):.1%}")

    print("\nSuggested score ranges for config/policies.json:")
    lower = 0
    for level, upper in zip(LEVELS, list(cuts) + [100]):
        print(f"  {level:<13} {lower:>3} to {upper}")
        lower = upper + 1


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sheet":
        make_sheet()
    elif command == "calibrate":
        calibrate()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
