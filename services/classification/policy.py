"""Applies the configured security policy for a classification. This is the
single point where "what must happen before this document may be printed" is
decided - the API layer must not make that call itself."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyDecision:
    classification: str
    require_alert: bool
    require_masking: bool
    require_watermark: bool
    require_footer: bool
    allow_printing: bool

    @property
    def can_auto_release(self) -> bool:
        """No user decision needed - e.g. PUBLIC/INTERNAL with no alert requirement."""
        return self.allow_printing and not self.require_alert


def evaluate_policy(classification: str, policy_row: dict) -> PolicyDecision:
    return PolicyDecision(
        classification=classification,
        require_alert=bool(policy_row.get("require_alert", False)),
        require_masking=bool(policy_row.get("require_masking", False)),
        require_watermark=bool(policy_row.get("require_watermark", False)),
        require_footer=bool(policy_row.get("require_footer", True)),
        allow_printing=bool(policy_row.get("allow_printing", True)),
    )
