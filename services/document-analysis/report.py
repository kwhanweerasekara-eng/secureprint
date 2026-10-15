"""Builds the detection report JSON and manages the short-lived, on-disk
working file that carries raw matched values between the detection stage and
the redaction stage. This working file is deleted as soon as sanitization
completes (or fails) - raw sensitive values are never written to the database.
"""
from __future__ import annotations

import json
from pathlib import Path

from detector import Detection


def build_report(job_id: str, filename: str, sha256: str, page_count: int, detections: list[Detection]) -> dict:
    categories: dict[str, int] = {}
    detection_list = []
    for d in detections:
        categories[d.category] = categories.get(d.category, 0) + 1
        detection_list.append(
            {
                "category": d.category,
                "page": d.page,
                "bbox": list(d.bbox) if d.bbox else None,
            }
        )
    return {
        "job_id": job_id,
        "document": {"name": filename, "sha256": sha256, "pages": page_count},
        "detections": detection_list,
        "categories": categories,
    }


def save_working_detections(processing_dir: Path, job_id: str, detections: list[Detection]) -> Path:
    """Persist detections WITH raw values to a private, short-lived working
    file so the redactor can verify sanitization later in the same job
    lifecycle. Caller is responsible for deleting this file after use."""
    path = processing_dir / f"{job_id}.detections.json"
    payload = [
        {
            "category": d.category,
            "page": d.page,
            "bbox": list(d.bbox) if d.bbox else None,
            "bboxes": [list(b) for b in d.bboxes] if d.bboxes else [],
            "value": d.value,
            "source": d.source,
            "rule_name": d.rule_name,
        }
        for d in detections
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def load_working_detections(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def delete_working_detections(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
