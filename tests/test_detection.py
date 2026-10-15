"""Unit tests for the detection engine: regex + keyword based detection."""
import json

import pytest

from tests.conftest import make_pdf


def load_rules_and_keywords(engine):
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
            enabled=True,
        )
        for name, c in patterns.items()
    ]
    return rules, keywords


def run_detection(engine, tmp_path, lines):
    pdf_path = make_pdf(tmp_path / "sample.pdf", lines)
    extraction = engine.extractor.extract_document(pdf_path)
    rules, keywords = load_rules_and_keywords(engine)
    detections = engine.detector.detect(extraction, rules, keywords)
    return detections, engine.detector.summarize_categories(detections)


def test_old_nic_detection(engine, tmp_path):
    detections, categories = run_detection(engine, tmp_path, ["NIC: 851234567V"])
    assert categories.get("nic") == 1
    assert detections[0].value == "851234567V"


def test_new_nic_detection(engine, tmp_path):
    detections, categories = run_detection(engine, tmp_path, ["NIC: 200012345678"])
    assert categories.get("nic") == 1


def test_email_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Contact: john.silva@example.com"])
    assert categories.get("email") == 1


def test_telephone_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Telephone: 0771234567"])
    assert categories.get("telephone") == 1


def test_payment_card_detection_valid_luhn(engine, tmp_path):
    # 4111111111111111 is a well-known Luhn-valid test Visa number
    _, categories = run_detection(engine, tmp_path, ["Card Number: 4111 1111 1111 1111"])
    assert categories.get("card") == 1


def test_payment_card_rejects_invalid_luhn(engine, tmp_path):
    # Same length, fails the Luhn checksum -> should NOT be flagged as a card
    _, categories = run_detection(engine, tmp_path, ["Reference: 1234 5678 9012 3456"])
    assert categories.get("card") is None


def test_bank_account_requires_context(engine, tmp_path):
    _, categories_with_context = run_detection(engine, tmp_path, ["Bank Account Number: 12345678"])
    assert categories_with_context.get("bank_account") is not None

    _, categories_without_context = run_detection(engine, tmp_path, ["Reference Number: 12345678"])
    assert categories_without_context.get("bank_account") is None


def test_credential_keyword_regex(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["password: Sup3rSecret!2026"])
    assert categories.get("credential") == 1


def test_salary_keyword_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Basic Salary: LKR 250,000"])
    assert categories.get("salary") is not None


def test_employee_id_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Employee ID: EMP-00123"])
    assert categories.get("employee_id") is not None


def test_classification_marker_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["CONFIDENTIAL"])
    assert categories.get("classification_marker") == 1


def test_no_detections_on_clean_document(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["This is a plain public notice with no sensitive data."])
    assert categories == {}


def test_detections_carry_bbox_and_page(engine, tmp_path):
    detections, _ = run_detection(engine, tmp_path, ["NIC: 200012345678"])
    assert len(detections) == 1
    d = detections[0]
    assert d.page == 0
    assert d.bbox is not None
    assert len(d.bbox) == 4


# ---------------------------------------------------------------------------
# New-format NIC plausibility (birth-year + day-of-year encoding)
# ---------------------------------------------------------------------------


def test_new_nic_rejects_implausible_day_of_year(engine, tmp_path):
    # birth year 2099 and day-of-year 912 are both impossible
    _, categories = run_detection(engine, tmp_path, ["NIC: 209991234561"])
    assert categories.get("nic") is None


def test_new_nic_accepts_plausible_female_day_of_year(engine, tmp_path):
    # year 2000, day 550 = a woman born on day 50 (501-866 is the female range)
    _, categories = run_detection(engine, tmp_path, ["NIC: 200055012345"])
    assert categories.get("nic") == 1


# ---------------------------------------------------------------------------
# Payment card network (IIN/BIN) validation
# ---------------------------------------------------------------------------


def _luhn_check_digit(prefix: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(prefix)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def test_card_rejects_luhn_valid_number_with_unknown_network_prefix(engine, tmp_path):
    prefix = "999988887777667"  # not a Visa/Mastercard/Amex/Discover/Diners/JCB range
    number = prefix + _luhn_check_digit(prefix)
    _, categories = run_detection(engine, tmp_path, [f"Reference Number: {number}"])
    assert categories.get("card") is None


def test_card_accepts_mastercard_range(engine, tmp_path):
    prefix = "551234567890123"  # 5512... falls in the legacy Mastercard 51-55 range
    number = prefix + _luhn_check_digit(prefix)
    _, categories = run_detection(engine, tmp_path, [f"Card Number: {number}"])
    assert categories.get("card") == 1


# ---------------------------------------------------------------------------
# Cloud / API credential detection
# ---------------------------------------------------------------------------


def test_aws_access_key_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"])
    assert categories.get("api_key") is not None


def test_google_api_key_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Maps key: AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY"])
    assert categories.get("api_key") is not None


def test_github_token_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["token: ghp_16C7e42F292c6912E7710c838347Ae178B4a"])
    assert categories.get("api_key") is not None


def test_stripe_key_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Stripe secret: sk_live_4eC39HqLyjWDarjtT1zdp7dc"])
    assert categories.get("api_key") is not None


def test_slack_token_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Slack bot token: xoxb-123456789012-abcdefghijklmnop"])
    assert categories.get("api_key") is not None


def test_jwt_bearer_token_detection(engine, tmp_path):
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    _, categories = run_detection(engine, tmp_path, [f"Authorization: Bearer {jwt}"])
    assert categories.get("api_key") is not None


def test_private_key_block_detection(engine, tmp_path):
    lines = [
        "-----BEGIN RSA PRIVATE KEY-----",
        "MIIEpAIBAAKCAQEA1c7+9z5Pad7OejecsQ0bu3aumqU=",
        "-----END RSA PRIVATE KEY-----",
    ]
    _, categories = run_detection(engine, tmp_path, lines)
    assert categories.get("api_key") is not None


def test_generic_secret_assignment_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["client_secret: mSup3rInternalOnlyValue"])
    assert categories.get("api_key") is not None


def test_credential_category_no_longer_catches_api_keys(engine, tmp_path):
    # api-key-style assignments should land under the new api_key category,
    # not be double counted as a generic "credential"
    _, categories = run_detection(engine, tmp_path, ["api_key: abc123XYZsecretvalue"])
    assert categories.get("api_key") is not None
    assert categories.get("credential") is None


# ---------------------------------------------------------------------------
# Passport and IBAN detection
# ---------------------------------------------------------------------------


def test_passport_legacy_format_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Passport No: N1234567"])
    assert categories.get("passport") is not None


def test_passport_requires_context_for_generic_format(engine, tmp_path):
    _, with_ctx = run_detection(engine, tmp_path, ["Passport Number: P1234561"])
    assert with_ctx.get("passport") is not None

    _, without_ctx = run_detection(engine, tmp_path, ["Reference Code: P1234561"])
    assert without_ctx.get("passport") is None


def test_iban_requires_context(engine, tmp_path):
    _, with_ctx = run_detection(engine, tmp_path, ["IBAN: GB29NWBK60161331926819"])
    assert with_ctx.get("iban") is not None

    _, without_ctx = run_detection(engine, tmp_path, ["Code: GB29NWBK60161331926819"])
    assert without_ctx.get("iban") is None


def iban_values(detections):
    return [d.value for d in detections if d.category == "iban" and d.source == "regex"]


@pytest.mark.parametrize("line, iban", [
    # On paper an IBAN is printed in groups of four; the value stops before SWIFT.
    ("IBAN: GB82 WEST 1234 5698 7654 32 SWIFT: NWBKGB2L", "GB82 WEST 1234 5698 7654 32"),
    # Last group is a full four, so a short word after it could pass for a group.
    ("IBAN BE68 5390 0754 7034 BIC GEBABEBB", "BE68 5390 0754 7034"),
    ("IBAN: NO93 8601 1117 947", "NO93 8601 1117 947"),  # shortest IBAN, 15 characters
])
def test_iban_printed_in_groups_of_four_is_detected(engine, tmp_path, line, iban):
    detections, _ = run_detection(engine, tmp_path, [line])
    assert iban_values(detections) == [iban]


def test_grouped_iban_is_not_split_by_the_card_rule(engine, tmp_path):
    # "4255 9100 0008 0121" inside this IBAN passes the Luhn check; the IBAN
    # rule must claim the whole value first so no group is left readable.
    detections, categories = run_detection(engine, tmp_path, ["IBAN: FR76 4255 9100 0008 0121 4567 890"])
    assert iban_values(detections) == ["FR76 4255 9100 0008 0121 4567 890"]
    assert categories.get("payment_card") is None


def test_iban_without_spaces_is_still_detected(engine, tmp_path):
    detections, _ = run_detection(engine, tmp_path, ["IBAN: GB82WEST12345698765432 SWIFT: NWBKGB2L"])
    assert iban_values(detections) == ["GB82WEST12345698765432"]


def test_grouped_iban_still_requires_the_iban_label(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Ref: GB82 WEST 1234 5698 7654 32"])
    assert categories.get("iban") is None


def test_grouped_iban_is_fully_redacted_and_passes_verification(engine, tmp_path):
    import fitz

    iban = "GB82 WEST 1234 5698 7654 32"
    pdf_path = make_pdf(tmp_path / "iban.pdf", ["Payment instruction", f"IBAN: {iban} SWIFT: NWBKGB2L"])
    extraction = engine.extractor.extract_document(pdf_path)
    rules, keywords = load_rules_and_keywords(engine)
    detections = engine.detector.detect(extraction, rules, keywords)
    assert iban_values(detections) == [iban]

    # Same targets as the pipeline: one box per visual line of each value.
    targets = [{"page": d.page, "bbox": list(b)} for d in detections for b in (d.bboxes or ([d.bbox] if d.bbox else []))]
    options = engine.processor.SanitizeOptions(
        require_masking=True, require_watermark=True, require_footer=True, footer_text="RESTRICTED | TEST | SP-TEST"
    )
    output_path = str(tmp_path / "iban_sanitized.pdf")
    engine.processor.sanitize_document(pdf_path, output_path, targets, options)

    # must not raise
    engine.redactor.assert_redaction_clean(output_path, [d.value for d in detections if d.bbox or d.bboxes])

    # Verification looks for the whole value, so also check each group: a box
    # that covered only part of the IBAN would leave a group readable.
    with fitz.open(output_path) as out:
        text = "\n".join(p.get_text() for p in out)
    for group in iban.split():
        assert group not in text
    assert "IBAN" in text and "SWIFT: NWBKGB2L" in text


def test_iban_rule_seeded_with_the_compact_only_pattern_is_upgraded(client):  # client: app started and seeded
    from apps.api.config import get_settings
    from apps.api.database.session import SessionLocal
    from apps.api.models.rule import DetectionRule
    from apps.api.services import seed

    shipped = json.loads((get_settings().config_dir / "patterns.json").read_text())["iban"]["pattern"]
    db = SessionLocal()
    try:
        row = db.query(DetectionRule).filter(DetectionRule.name == "iban").one()
        row.pattern = seed._SUPERSEDED_PATTERNS["iban"]  # as an older install left it
        row.priority = 65
        db.commit()

        seed.upgrade_builtin_rules(db)
        db.refresh(row)
        assert row.pattern == shipped
        assert row.priority == 92
    finally:
        row.pattern = shipped
        db.commit()
        db.close()


def test_international_telephone_format_detection(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Telephone: +94 771234567"])
    assert categories.get("telephone") == 1
