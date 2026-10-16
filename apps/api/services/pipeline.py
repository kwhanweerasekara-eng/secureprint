"""Orchestrates the SecurePrint analysis and sanitization pipeline.

INSPECTION -> CLASSIFICATION -> POLICY -> SANITIZATION -> PRINTING

This module owns every state transition of a PrintJob. It is deliberately
fail-closed: any unexpected exception anywhere in analysis or sanitization
results in the job being moved to FAILED/BLOCKED and the original document
being deleted - it is never released for printing.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database.session import SessionLocal
from apps.api.models.audit import AuditEvent
from apps.api.models.detection import DetectionSummary
from apps.api.models.enums import AuditEventType, BlockReason, Classification, JobAction, JobStatus
from apps.api.models.policy import ClassificationPolicy
from apps.api.models.print_job import PrintJob
from apps.api.models.rule import DetectionRule, Keyword, RiskWeight
from apps.api.models.settings import SystemSetting
from apps.api.services import engine_loader as eng

settings = get_settings()

FAIL_CLOSED_MESSAGE = "SecurePrint processing failed. Print job has been blocked for security."


def _audit(db: Session, *, job_id: str | None, user_id: str | None, event_type: AuditEventType, message: str = "", metadata: dict | None = None):
    return eng.audit_service.record_event(
        db,
        AuditEvent,
        event_type=event_type.value,
        job_id=job_id,
        user_id=user_id,
        message=message,
        metadata=metadata,
    )


def _load_rules(db: Session) -> list:
    rows = db.query(DetectionRule).filter(DetectionRule.enabled == True).all()  # noqa: E712
    return [
        eng.detector.PatternRule(
            name=r.name,
            category=r.category,
            pattern=r.pattern,
            priority=r.priority,
            requires_keyword_context=r.requires_keyword_context,
            context_keywords=[k for k in (r.context_keywords or "").split(",") if k],
            enabled=r.enabled,
        )
        for r in rows
    ]


def _load_keywords(db: Session) -> dict[str, list[str]]:
    rows = db.query(Keyword).filter(Keyword.enabled == True).all()  # noqa: E712
    out: dict[str, list[str]] = {}
    for k in rows:
        out.setdefault(k.category, []).append(k.term)
    return out


def _load_weights(db: Session) -> dict[str, int]:
    rows = db.query(RiskWeight).filter(RiskWeight.enabled == True).all()  # noqa: E712
    return {w.category: w.weight for w in rows}


def _load_category_floors(db: Session) -> dict[str, str]:
    """Minimum classification per category (e.g. a real password makes a page
    RESTRICTED). An admin can override the shipped defaults from
    config/weights.json with a "category_floors" system setting."""
    row = db.get(SystemSetting, "category_floors")
    if row and row.value:
        return row.value
    weights_cfg = json.loads((settings.config_dir / "weights.json").read_text(encoding="utf-8"))
    return {c: cfg["min_classification"] for c, cfg in weights_cfg.items() if cfg.get("min_classification")}


def _load_thresholds(db: Session) -> list:
    rows = db.query(ClassificationPolicy).all()
    return [
        eng.classifier.ClassificationThreshold(classification=p.classification.value, min_score=p.min_score, max_score=p.max_score)
        for p in rows
    ]


def _watermark_config(db: Session) -> dict:
    row = db.get(SystemSetting, "watermark_config")
    if row and row.value:
        return row.value
    return {"text": "RESTRICTED", "opacity": 0.10, "font_size": 26, "angle": 45}


def _watermark_text(wm_cfg: dict, classification: Classification) -> str:
    """The configured text, except that a level name (the default is
    "RESTRICTED") becomes the document's own level, so a page is never
    stamped with a level it does not have."""
    text = (wm_cfg.get("text") or "").strip()
    if not text or text.upper() in {c.value for c in Classification}:
        return classification.value
    return text


def _fail_closed(db: Session, job: PrintJob, message: str, event_type: AuditEventType = AuditEventType.FAILED) -> None:
    job.status = JobStatus.FAILED
    job.block_reason = BlockReason.PROCESSING_FAILURE
    job.action = JobAction.BLOCKED
    job.status_message = FAIL_CLOSED_MESSAGE
    if job.original_path:
        Path(job.original_path).unlink(missing_ok=True)
        job.original_path = None
    db.commit()
    _audit(db, job_id=job.id, user_id=None, event_type=event_type, message=message)


def run_analysis_pipeline(job_id: str) -> None:
    db = SessionLocal()
    started_at = time.perf_counter()
    try:
        job = db.get(PrintJob, job_id)
        if job is None:
            return

        job.status = JobStatus.ANALYZING
        db.commit()
        _audit(db, job_id=job.id, user_id=job.user_id, event_type=AuditEventType.ANALYSIS_STARTED)

        extraction = eng.extractor.extract_document(job.original_path)
        job.page_count = extraction.page_count
        job.has_text_layer = extraction.has_text_layer
        db.commit()

        if not extraction.has_text_layer:
            job.status = JobStatus.BLOCKED
            job.block_reason = BlockReason.SCANNED_DOCUMENT
            job.action = JobAction.BLOCKED
            job.status_message = (
                "SCAN / IMAGE-ONLY DOCUMENT DETECTED. Unable to perform text-based security analysis. OCR is required."
            )
            if job.original_path:
                Path(job.original_path).unlink(missing_ok=True)
                job.original_path = None
            db.commit()
            _audit(db, job_id=job.id, user_id=job.user_id, event_type=AuditEventType.NO_TEXT_LAYER, message=job.status_message)
            return

        rules = _load_rules(db)
        keywords = _load_keywords(db)
        detections = eng.detector.detect(extraction, rules, keywords)
        categories = eng.detector.summarize_categories(detections)

        job.status = JobStatus.DETECTED
        db.commit()
        for category, count in categories.items():
            db.add(DetectionSummary(job_id=job.id, category=category, count=count))
        db.commit()
        _audit(
            db,
            job_id=job.id,
            user_id=job.user_id,
            event_type=AuditEventType.DATA_DETECTED,
            message=f"{len(detections)} sensitive item(s) detected across {len(categories)} categor(y/ies)",
            metadata={"categories": categories},
        )

        weights = _load_weights(db)
        score = eng.scorer.calculate_risk(categories, weights)
        job.risk_score = score
        db.commit()
        # Points each distinct category added, kept with the job so the score
        # can be explained later even if an admin changes the weights.
        contributions = {c: weights.get(c, 0) for c, n in sorted(categories.items()) if n > 0}
        _audit(
            db,
            job_id=job.id,
            user_id=job.user_id,
            event_type=AuditEventType.RISK_SCORED,
            metadata={"risk_score": score, "contributions": contributions, "uncapped_score": sum(contributions.values())},
        )

        thresholds = _load_thresholds(db)
        score_level = eng.classifier.classify(score, thresholds)
        floors = _load_category_floors(db)
        found_values = eng.detector.value_categories(detections)
        classification_str = eng.classifier.apply_floors(score_level, found_values, floors)
        raised_by = sorted(c for c in found_values if floors.get(c) == classification_str) if classification_str != score_level else []
        job.classification = Classification(classification_str)
        job.status = JobStatus.CLASSIFIED
        job.processing_time_ms = int((time.perf_counter() - started_at) * 1000)
        db.commit()
        _audit(
            db,
            job_id=job.id,
            user_id=job.user_id,
            event_type=AuditEventType.CLASSIFIED,
            message=f"Classification: {classification_str}"
            + (f" (raised from {score_level} by the sensitive data found)" if classification_str != score_level else ""),
            metadata={
                "risk_score": score,
                "classification": classification_str,
                "score_classification": score_level,
                "raised_by": raised_by,
            },
        )

        policy_row = db.query(ClassificationPolicy).filter(ClassificationPolicy.classification == job.classification).first()
        decision = eng.policy_engine.evaluate_policy(
            classification_str,
            {
                "require_alert": policy_row.require_alert,
                "require_masking": policy_row.require_masking,
                "require_watermark": policy_row.require_watermark,
                "require_footer": policy_row.require_footer,
                "allow_printing": policy_row.allow_printing,
            },
        )

        working_path = eng.report.save_working_detections(settings.processing_dir, job.id, detections)

        if not decision.allow_printing:
            job.status = JobStatus.BLOCKED
            job.block_reason = BlockReason.POLICY_DENIED
            job.action = JobAction.BLOCKED
            job.status_message = "Security policy denies printing for this classification."
            if job.original_path:
                Path(job.original_path).unlink(missing_ok=True)
                job.original_path = None
            db.commit()
            eng.report.delete_working_detections(working_path)
            _audit(db, job_id=job.id, user_id=job.user_id, event_type=AuditEventType.BLOCKED, message=job.status_message)
            return

        if decision.can_auto_release:
            _perform_sanitization(db, job, decided_by=None)
        else:
            job.status = JobStatus.AWAITING_DECISION
            db.commit()
            _audit(db, job_id=job.id, user_id=job.user_id, event_type=AuditEventType.AWAITING_DECISION)

    except Exception as exc:  # noqa: BLE001 - fail closed on ANY error
        db.rollback()
        job = db.get(PrintJob, job_id)
        if job is not None:
            _fail_closed(db, job, f"Analysis failed: {exc}")
    finally:
        db.close()


def _perform_sanitization(db: Session, job: PrintJob, decided_by: str | None) -> None:
    working_path = settings.processing_dir / f"{job.id}.detections.json"
    if not working_path.exists():
        _fail_closed(db, job, "Working detection data missing - cannot safely sanitize")
        return

    job.status = JobStatus.SANITIZING
    job.decided_by = decided_by
    job.decided_at = datetime.utcnow()
    db.commit()
    _audit(
        db,
        job_id=job.id,
        user_id=decided_by,
        event_type=AuditEventType.DECISION_MASK if decided_by else AuditEventType.SANITIZING,
    )

    try:
        raw_detections = eng.report.load_working_detections(working_path)
        policy_row = db.query(ClassificationPolicy).filter(ClassificationPolicy.classification == job.classification).first()
        wm_cfg = _watermark_config(db)

        footer_text = eng.processor.build_footer_text(
            job.classification.value, job.id, settings.organisation_name, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        )

        options = eng.processor.SanitizeOptions(
            require_masking=policy_row.require_masking,
            require_watermark=policy_row.require_watermark,
            require_footer=policy_row.require_footer,
            watermark_text=_watermark_text(wm_cfg, job.classification),
            watermark_opacity=wm_cfg.get("opacity", 0.10),
            watermark_font_size=wm_cfg.get("font_size", 26),
            watermark_angle=wm_cfg.get("angle", 45),
            footer_text=footer_text,
        )

        sanitized_path = settings.sanitized_dir / f"{job.id}.pdf"
        redaction_targets = []
        for d in raw_detections:
            per_line = d.get("bboxes") or []
            if per_line:
                for b in per_line:
                    redaction_targets.append({"page": d["page"], "bbox": b})
            elif d.get("bbox"):
                redaction_targets.append({"page": d["page"], "bbox": d["bbox"]})

        redactions_applied = eng.processor.sanitize_document(job.original_path, str(sanitized_path), redaction_targets, options)

        if options.require_masking:
            raw_values = [d["value"] for d in raw_detections if d.get("bbox") or d.get("bboxes")]
            eng.redactor.assert_redaction_clean(str(sanitized_path), raw_values)

        job.sanitized_path = str(sanitized_path)
        job.status = JobStatus.READY
        job.action = JobAction.MASK_AND_PRINT if options.require_masking else JobAction.ALLOW_PRINT

        if job.original_path:
            Path(job.original_path).unlink(missing_ok=True)
            job.original_path = None

        db.commit()
        eng.report.delete_working_detections(working_path)
        _audit(
            db,
            job_id=job.id,
            user_id=decided_by,
            event_type=AuditEventType.SANITIZED,
            message=f"{redactions_applied} region(s) redacted",
            metadata={"redactions_applied": redactions_applied},
        )

    except eng.redactor.RedactionVerificationError as exc:
        _fail_closed(db, job, str(exc), event_type=AuditEventType.REDACTION_VERIFICATION_FAILED)
    except Exception as exc:  # noqa: BLE001
        _fail_closed(db, job, f"Sanitization failed: {exc}")


def approve_mask_and_continue(job_id: str, decided_by: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(PrintJob, job_id)
        if job is None or job.status != JobStatus.AWAITING_DECISION:
            return
        _perform_sanitization(db, job, decided_by)
    finally:
        db.close()


def cancel_job(job_id: str, decided_by: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(PrintJob, job_id)
        if job is None:
            return
        job.status = JobStatus.CANCELLED
        job.action = JobAction.CANCELLED
        job.block_reason = BlockReason.USER_CANCELLED
        job.decided_by = decided_by
        job.decided_at = datetime.utcnow()
        if job.original_path:
            Path(job.original_path).unlink(missing_ok=True)
            job.original_path = None
        db.commit()
        working_path = settings.processing_dir / f"{job.id}.detections.json"
        eng.report.delete_working_detections(working_path)
        _audit(db, job_id=job.id, user_id=decided_by, event_type=AuditEventType.DECISION_CANCEL)
    finally:
        db.close()
