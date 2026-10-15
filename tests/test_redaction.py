"""Critical redaction tests (spec section 22, 50).

A black rectangle drawn over live text underneath is a failed implementation.
These tests reopen the sanitized output and prove the raw value cannot be
extracted as text - not just visually covered.
"""
from tests.conftest import make_pdf


def test_redacted_nic_is_not_extractable(engine, tmp_path):
    pdf_path = make_pdf(tmp_path / "nic.pdf", ["NIC: 200012345678"])
    extraction = engine.extractor.extract_document(pdf_path)

    bbox = extraction.pages[0].offsets  # sanity: extraction produced offsets
    assert bbox

    # locate the NIC span directly for a controlled, minimal redaction test
    text = extraction.pages[0].text
    start = text.index("200012345678")
    end = start + len("200012345678")
    rect = engine.extractor.bbox_for_span(extraction.pages[0], start, end)
    assert rect is not None

    import fitz

    doc = fitz.open(pdf_path)
    detections = [{"page": 0, "bbox": list(rect)}]
    engine.redactor.redact_pdf(doc, detections)
    output_path = str(tmp_path / "nic_sanitized.pdf")
    doc.save(output_path)
    doc.close()

    leaked = engine.redactor.verify_no_raw_values(output_path, ["200012345678"])
    assert leaked == []

    # Also confirm via a fresh direct extraction that the digits are gone
    reopened = fitz.open(output_path)
    full_text = "\n".join(p.get_text() for p in reopened)
    reopened.close()
    assert "200012345678" not in full_text


def test_redaction_verification_raises_on_leak(engine, tmp_path):
    pdf_path = make_pdf(tmp_path / "leak.pdf", ["Unrelated content, nothing redacted here."])
    import fitz

    doc = fitz.open(pdf_path)
    doc.save(str(tmp_path / "not_actually_redacted.pdf"))
    doc.close()

    try:
        engine.redactor.assert_redaction_clean(
            str(tmp_path / "not_actually_redacted.pdf"), ["Unrelated content, nothing redacted here."]
        )
        assert False, "expected RedactionVerificationError"
    except engine.redactor.RedactionVerificationError:
        pass


def test_full_sanitize_pipeline_removes_all_raw_values(engine, tmp_path):
    lines = ["NIC: 200012345678", "Bank Account Number: 123456789012", "password: Sup3rSecret!2026"]
    pdf_path = make_pdf(tmp_path / "full.pdf", lines)
    extraction = engine.extractor.extract_document(pdf_path)

    import json

    import apps.api.config as cfg

    settings = cfg.get_settings()
    patterns = json.loads((settings.config_dir / "patterns.json").read_text())
    keywords = json.loads((settings.config_dir / "keywords.json").read_text())
    rules = [
        engine.detector.PatternRule(
            name=name,
            category=c["category"],
            pattern=c["pattern"],
            priority=c.get("priority", 50),
            requires_keyword_context=c.get("requires_keyword_context", False),
            context_keywords=c.get("context_keywords", []),
        )
        for name, c in patterns.items()
    ]
    detections = engine.detector.detect(extraction, rules, keywords)
    # Keyword hits are field labels ("Account", "password") that stay visible
    # by design and have no bbox; the pipeline only verifies redacted values.
    raw_values = [d.value for d in detections if d.bbox]
    assert raw_values, "expected regex detections to verify"
    redaction_targets = [{"page": d.page, "bbox": list(d.bbox)} for d in detections if d.bbox]

    options = engine.processor.SanitizeOptions(
        require_masking=True, require_watermark=True, require_footer=True, footer_text="RESTRICTED | TEST | SP-TEST"
    )
    output_path = str(tmp_path / "full_sanitized.pdf")
    engine.processor.sanitize_document(pdf_path, output_path, redaction_targets, options)

    # must not raise
    engine.redactor.assert_redaction_clean(output_path, raw_values)


def test_watermark_and_footer_visible_in_output(engine, tmp_path):
    pdf_path = make_pdf(tmp_path / "wm.pdf", ["PUBLIC NOTICE"])
    import fitz

    doc = fitz.open(pdf_path)
    engine.watermark.apply_watermark(doc, text="RESTRICTED")
    engine.footer.apply_footer(doc, "RESTRICTED | SECUREPRINT PROTECTED | SP-TEST")
    output_path = str(tmp_path / "wm_sanitized.pdf")
    doc.save(output_path)
    doc.close()

    reopened = fitz.open(output_path)
    full_text = "\n".join(p.get_text() for p in reopened)
    reopened.close()
    assert "RESTRICTED" in full_text
    assert "SP-TEST" in full_text


def test_stacked_boxes_with_offset_left_edges_are_both_redacted(engine, tmp_path):
    # Regression: two values stacked in a column, the lower one starting 2pt
    # further left. Merging their boxes used to keep only the lower value's
    # top edge, so the upper value (here a card number) stayed readable.
    import fitz

    upper, lower = "5555 5555 5555 4444", "0012 3456 7890"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((146, 574), upper, fontsize=9.5)
    page.insert_text((144, 588), lower, fontsize=9.5)
    detections = [{"page": 0, "bbox": list(page.search_for(value)[0])} for value in (upper, lower)]
    engine.redactor.redact_pdf(doc, detections)
    output_path = str(tmp_path / "stacked_sanitized.pdf")
    doc.save(output_path)
    doc.close()

    assert engine.redactor.verify_no_raw_values(output_path, [upper, lower]) == []
