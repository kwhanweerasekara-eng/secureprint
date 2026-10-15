"""Processing-time benchmark (proposal 3.9: a 20-page document in under three
seconds; test case T07: a 100-page document).

Builds multi-page documents in two profiles (typical office pages, and dense
payroll pages as the worst case) and times the full server-side path a RESTRICTED print job takes:
extract -> detect -> score -> classify -> mask -> watermark -> footer ->
save -> re-open and verify that no masked value is still readable.

Network transfer and the time a user spends reading the alert are not
included; they are reported separately in the dissertation.

Usage:
    python tests/evaluation/realistic/benchmark_latency.py
"""
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
from run_realistic import analyse, load_rules_and_config, mask  # noqa: E402  (also sets up engine paths)
import redactor  # noqa: E402

PAGE_COUNTS = [1, 5, 20, 50, 100]
RUNS = 3
TARGET_MS_20_PAGES = 3000
REPORT_PATH = HERE / "latency.json"

# Two profiles: "typical" office pages (letters, records, minutes, forms, a
# few sensitive values per page) and "dense" payroll pages (about 50 rows per
# page, five sensitive values per row) as the worst case.
TYPICAL_MAKERS = [corpus.employee_record, corpus.minutes, corpus.increment_letter, corpus.invoice,
                  corpus.travel_request, corpus.procedure, corpus.leave_form, corpus.cv]


def build(profile: str, pages: int, path: Path) -> int:
    f = corpus.Faker(pages)
    if profile == "dense":
        rows = 54 * pages - 6
        while True:
            corpus.render(corpus.payroll(f, rows), path)
            with corpus.fitz.open(str(path)) as d:
                if d.page_count >= pages:
                    return d.page_count
            rows += 10
    # typical: one short document per page, each starting on a new page
    doc = corpus.Doc("bundle", f"Bundle of {pages}", "CONFIDENTIAL", [])
    for i in range(pages):
        doc.blocks.append(("newpage", None)) if i else None
        doc.blocks.extend(TYPICAL_MAKERS[i % len(TYPICAL_MAKERS)](f).blocks)
    corpus.render(doc, path)
    with corpus.fitz.open(str(path)) as d:
        return d.page_count


def main() -> None:
    rules, keywords, weights, thresholds = load_rules_and_config()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for profile, pages in [(p, n) for p in ("typical", "dense") for n in PAGE_COUNTS]:
            src = Path(tmp) / f"{profile}_{pages}.pdf"
            build(profile, pages, src)
            timings = []
            for run in range(RUNS):
                out = Path(tmp) / f"out_{pages}_{run}.pdf"
                started = time.perf_counter()
                extraction, detections, _cats, _score, level, _ = analyse(src, rules, keywords, weights, thresholds)
                mask(src, detections, out)
                redactor.verify_no_raw_values(str(out), [d.value for d in detections if d.bbox])
                timings.append((time.perf_counter() - started) * 1000)
            row = {
                "profile": profile,
                "pages": extraction.page_count,
                "detections": len(detections),
                "classification": level,
                "median_ms": round(statistics.median(timings), 1),
                "max_ms": round(max(timings), 1),
            }
            results.append(row)
            print(f"{profile:<8}{row['pages']:>4} pages  {row['detections']:>5} detections  "
                  f"median {row['median_ms']:>8.1f} ms  max {row['max_ms']:>8.1f} ms")

    print()
    for twenty in (r for r in results if r["pages"] == 20):
        verdict = "meets" if twenty["max_ms"] < TARGET_MS_20_PAGES else "misses"
        print(f"20 pages, {twenty['profile']}: {twenty['max_ms']:.0f} ms worst run - {verdict} the "
              f"{TARGET_MS_20_PAGES} ms target.")
    REPORT_PATH.write_text(json.dumps({"runs": RUNS,
                                       "target_ms_20_pages": TARGET_MS_20_PAGES, "results": results}, indent=2))
    print(f"Written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
