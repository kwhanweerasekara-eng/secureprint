"""Policy engine decisions per classification (spec section 20)."""


def test_public_policy_allows_print_without_alert(engine):
    decision = engine.policy_engine.evaluate_policy(
        "PUBLIC",
        {"require_alert": False, "require_masking": False, "require_watermark": False, "require_footer": True, "allow_printing": True},
    )
    assert decision.can_auto_release is True
    assert decision.require_masking is False


def test_confidential_requires_alert_and_masking(engine):
    decision = engine.policy_engine.evaluate_policy(
        "CONFIDENTIAL",
        {"require_alert": True, "require_masking": True, "require_watermark": False, "require_footer": True, "allow_printing": True},
    )
    assert decision.can_auto_release is False
    assert decision.require_masking is True
    assert decision.require_watermark is False


def test_restricted_requires_alert_masking_and_watermark(engine):
    decision = engine.policy_engine.evaluate_policy(
        "RESTRICTED",
        {"require_alert": True, "require_masking": True, "require_watermark": True, "require_footer": True, "allow_printing": True},
    )
    assert decision.can_auto_release is False
    assert decision.require_masking is True
    assert decision.require_watermark is True


def test_policy_denying_printing_never_auto_releases(engine):
    decision = engine.policy_engine.evaluate_policy(
        "RESTRICTED",
        {"require_alert": True, "require_masking": True, "require_watermark": True, "require_footer": True, "allow_printing": False},
    )
    assert decision.can_auto_release is False
    assert decision.allow_printing is False


def test_watermark_names_the_documents_own_level():
    # The default watermark text is "RESTRICTED". If an admin turns the
    # watermark on for another level, the page must not claim to be RESTRICTED.
    from apps.api.models.enums import Classification
    from apps.api.services.pipeline import _watermark_text

    default = {"text": "RESTRICTED"}
    assert _watermark_text(default, Classification.PUBLIC) == "PUBLIC"
    assert _watermark_text(default, Classification.RESTRICTED) == "RESTRICTED"
    assert _watermark_text({"text": ""}, Classification.CONFIDENTIAL) == "CONFIDENTIAL"
    assert _watermark_text({"text": "DO NOT COPY"}, Classification.PUBLIC) == "DO NOT COPY"
