"""Real PDF redaction using PyMuPDF's redaction annotations.

CRITICAL: apply_redactions() actually removes the underlying text/graphics
content beneath the annotation, unlike simply drawing a black rectangle over
the page. After redaction we reopen the saved file and re-extract its text to
verify that none of the original raw sensitive values survive. If the
verification fails, the caller must NOT release the file - this module raises
so the pipeline fails closed.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


REDACTION_BATCH = 25
PADDING = 2.0
ROW_BUCKET = 20.0


class RedactionVerificationError(Exception):
    """Raised when a sanitized PDF still contains a raw sensitive value."""


def redact_pdf(doc: fitz.Document, detections: list[dict]) -> int:
    """Apply redactions in-place on an already-open fitz.Document.

    detections: list of {"page": int, "bbox": [x0,y0,x1,y1]}
    Returns the number of redaction boxes applied.
    """
    by_page: dict[int, list[list[float]]] = {}
    for d in detections:
        if not d.get("bbox"):
            continue
        by_page.setdefault(d["page"], []).append(d["bbox"])

    applied = 0
    for page_number, boxes in by_page.items():
        if page_number >= doc.page_count:
            continue
        page = doc[page_number]
        rects = _merge_column_runs(page, [_padded(b) for b in boxes])
        # Adding a redaction annotation gets slower the more a page already
        # has, so very dense pages are redacted in batches.
        for i in range(0, len(rects), REDACTION_BATCH):
            for rect in rects[i:i + REDACTION_BATCH]:
                page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
        applied += len(boxes)
    return applied


def _padded(bbox) -> fitz.Rect:
    rect = fitz.Rect(*bbox)
    return fitz.Rect(rect.x0 - PADDING, rect.y0 - PADDING, rect.x1 + PADDING, rect.y1 + PADDING)


def _merge_column_runs(page: fitz.Page, rects: list[fitz.Rect]) -> list[fitz.Rect]:
    """Joins redaction boxes stacked directly on top of each other in the same
    column (a salary column on a payroll sheet) into one box. A payroll page
    then needs a handful of redactions instead of hundreds, which is what
    makes dense pages slow. Boxes are only joined when the joined box would
    not cover any other text, so nothing outside the detected values is
    blacked out."""
    if len(rects) < 2:
        return rects
    boxes = [(r.x0, r.y0, r.x1, r.y1) for r in rects]
    by_row: dict[int, list[tuple]] = {}
    for bx in boxes:
        for k in range(int(bx[1] // ROW_BUCKET), int(bx[3] // ROW_BUCKET) + 1):
            by_row.setdefault(k, []).append(bx)

    others_by_row: dict[int, list[tuple]] = {}
    for w in page.get_text("words"):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        near = by_row.get(int(cy // ROW_BUCKET), [])
        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in near):
            continue
        # shrink slightly so a neighbour that merely touches the edge doesn't block the join
        word = (w[0] + 0.5, w[1] + 0.5, w[2] - 0.5, w[3] - 0.5)
        for k in range(int(word[1] // ROW_BUCKET), int(word[3] // ROW_BUCKET) + 1):
            others_by_row.setdefault(k, []).append(word)

    def covers_other_text(b) -> bool:
        for k in range(int(b[1] // ROW_BUCKET), int(b[3] // ROW_BUCKET) + 1):
            for o in others_by_row.get(k, []):
                if o[0] < b[2] and o[2] > b[0] and o[1] < b[3] and o[3] > b[1]:
                    return True
        return False

    merged: list[tuple] = []
    for bx in sorted(boxes, key=lambda b: (round(b[0]), b[1])):
        if merged:
            last = merged[-1]
            # Sorting by left edge can put the lower box first when its left
            # edge is a little further left, so measure the gap both ways and
            # keep both tops - otherwise the upper value drops out of the box.
            gap = max(bx[1] - last[3], last[1] - bx[3])
            if abs(bx[0] - last[0]) < 3 and gap <= 1:
                joined = (min(last[0], bx[0]), min(last[1], bx[1]), max(last[2], bx[2]), max(last[3], bx[3]))
                if not covers_other_text(joined):
                    merged[-1] = joined
                    continue
        merged.append(bx)
    return [fitz.Rect(*b) for b in merged]


def verify_no_raw_values(sanitized_path: str, raw_values: list[str]) -> list[str]:
    """Reopens the sanitized PDF and checks that none of the raw sensitive
    values are still extractable. Returns a list of values that leaked (empty
    list means verification passed)."""
    leaked: list[str] = []
    doc = fitz.open(sanitized_path)
    try:
        full_text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    for value in raw_values:
        v = value.strip()
        if len(v) < 3:
            continue
        if v in full_text:
            leaked.append(v)
    return leaked


def assert_redaction_clean(sanitized_path: str, raw_values: list[str]) -> None:
    leaked = verify_no_raw_values(sanitized_path, raw_values)
    if leaked:
        try:
            Path(sanitized_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise RedactionVerificationError(
            f"Redaction verification failed: {len(leaked)} sensitive value(s) still extractable from output PDF"
        )
