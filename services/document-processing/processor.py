"""Orchestrates the sanitization stage: redact -> watermark -> footer -> save,
against a single open document, then hands off to the caller for the mandatory
post-save redaction verification (see redactor.assert_redaction_clean)."""
from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF
from footer import apply_footer, build_footer_text
from orientation import straighten_pages
from redactor import redact_pdf
from watermark import apply_watermark


@dataclass
class SanitizeOptions:
    require_masking: bool
    require_watermark: bool
    require_footer: bool
    watermark_text: str = "RESTRICTED"
    watermark_opacity: float = 0.18
    watermark_font_size: int = 64
    watermark_angle: float = 45
    footer_text: str = ""


def sanitize_document(input_path: str, output_path: str, detections: list[dict], options: SanitizeOptions) -> int:
    doc = fitz.open(input_path)
    redactions_applied = 0
    try:
        if options.require_masking and detections:
            redactions_applied = redact_pdf(doc, detections)

        # After redaction, which works in the page's original coordinates.
        straighten_pages(doc)

        if options.require_watermark:
            apply_watermark(
                doc,
                text=options.watermark_text,
                opacity=options.watermark_opacity,
                font_size=options.watermark_font_size,
                angle=options.watermark_angle,
            )

        if options.require_footer and options.footer_text:
            apply_footer(doc, options.footer_text)

        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()

    return redactions_applied


__all__ = ["SanitizeOptions", "sanitize_document", "build_footer_text"]
