"""Seeds the database with default detection rules, keywords, risk weights,
classification policies, and a default admin account. Idempotent - safe to
call on every startup."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.enums import Classification, UserRole
from apps.api.models.policy import ClassificationPolicy
from apps.api.models.rule import DetectionRule, Keyword, RiskWeight
from apps.api.models.user import User
from apps.api.security.auth import hash_password

settings = get_settings()


def _load_json(name: str) -> dict:
    path = settings.config_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


def seed_detection_rules(db: Session) -> None:
    """Inserts any rule from config/patterns.json that isn't already present
    (matched by name). Existing rows are left untouched, so an admin's
    enabled/disabled/weight edits survive a redeploy that adds new rules."""
    existing_names = {r.name for r in db.query(DetectionRule.name).all()}
    patterns = _load_json("patterns.json")
    added = False
    for name, cfg in patterns.items():
        if name in existing_names:
            continue
        db.add(
            DetectionRule(
                id=str(uuid.uuid4()),
                name=name,
                category=cfg["category"],
                pattern=cfg["pattern"],
                description=cfg.get("description", ""),
                priority=cfg.get("priority", 50),
                requires_keyword_context=cfg.get("requires_keyword_context", False),
                context_keywords=",".join(cfg.get("context_keywords", [])),
                enabled=cfg.get("enabled", True),
            )
        )
        added = True
    if added:
        db.commit()


# Built-in rules whose shipped definition has since been improved, keyed by
# rule name, with the pattern each one was originally seeded with. A row that
# still has that exact pattern was never edited by an admin, so it is safe to
# upgrade it to the current config/patterns.json definition. Edited rows are
# left alone.
_SUPERSEDED_PATTERNS = {
    "telephone": r"\b0\d{9}\b|(?<!\d)\+94[-\s]?\d{9}\b",
    "credential": r"(?i)\b(password|passwd|passphrase|pwd)\s*[:=]\s*\S+",
    "salary_amount": r"(?i)\b(?:LKR|Rs\.?|USD)\s?[\d,]+(?:\.\d{2})?\b",
    "bank_account_context": r"\b\d{8,16}\b",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
}


def upgrade_builtin_rules(db: Session) -> None:
    patterns = _load_json("patterns.json")
    changed = False
    for name, old_pattern in _SUPERSEDED_PATTERNS.items():
        row = db.query(DetectionRule).filter(DetectionRule.name == name).first()
        cfg = patterns.get(name)
        if row is None or cfg is None or row.pattern != old_pattern:
            continue
        row.pattern = cfg["pattern"]
        row.priority = cfg.get("priority", row.priority)
        row.description = cfg.get("description", row.description)
        row.requires_keyword_context = cfg.get("requires_keyword_context", False)
        row.context_keywords = ",".join(cfg.get("context_keywords", []))
        changed = True
    if changed:
        db.commit()


def seed_keywords(db: Session) -> None:
    """Inserts any (category, term) pair from config/keywords.json that isn't
    already present. Existing rows (including any an admin disabled) are left
    untouched."""
    existing_pairs = {(k.category, k.term.lower()) for k in db.query(Keyword.category, Keyword.term).all()}
    keywords = _load_json("keywords.json")
    added = False
    for category, terms in keywords.items():
        for term in terms:
            if (category, term.lower()) in existing_pairs:
                continue
            db.add(Keyword(id=str(uuid.uuid4()), category=category, term=term, enabled=True))
            added = True
    if added:
        db.commit()


def seed_risk_weights(db: Session) -> None:
    """Inserts any category from config/weights.json that doesn't have a
    RiskWeight row yet. An admin's weight/enabled edits on existing
    categories are left untouched."""
    existing_categories = {w.category for w in db.query(RiskWeight.category).all()}
    weights = _load_json("weights.json")
    added = False
    for category, cfg in weights.items():
        if category in existing_categories:
            continue
        db.add(
            RiskWeight(
                id=str(uuid.uuid4()),
                category=category,
                label=cfg["label"],
                weight=cfg["weight"],
                enabled=True,
            )
        )
        added = True
    if added:
        db.commit()


def seed_policies(db: Session) -> None:
    if db.query(ClassificationPolicy).count() > 0:
        return
    policies = _load_json("policies.json")
    for classification, cfg in policies.items():
        db.add(
            ClassificationPolicy(
                id=str(uuid.uuid4()),
                classification=Classification(classification),
                min_score=cfg["min_score"],
                max_score=cfg["max_score"],
                require_alert=cfg["require_alert"],
                require_masking=cfg["require_masking"],
                require_watermark=cfg["require_watermark"],
                require_footer=cfg["require_footer"],
                allow_printing=cfg["allow_printing"],
            )
        )
    db.commit()


def seed_default_admin(db: Session) -> None:
    if db.query(User).filter(User.role == UserRole.ADMIN).first():
        return
    admin = User(
        email="admin@secureprint.local",
        username="admin",
        full_name="SecurePrint Administrator",
        password_hash=hash_password(settings.default_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    staff = User(
        email="staff@secureprint.local",
        username="staff",
        full_name="Demo Staff User",
        password_hash=hash_password(settings.default_staff_password),
        role=UserRole.USER,
        is_active=True,
    )
    db.add_all([admin, staff])
    db.commit()


def run_all_seeds(db: Session) -> None:
    seed_detection_rules(db)
    upgrade_builtin_rules(db)
    seed_keywords(db)
    seed_risk_weights(db)
    seed_policies(db)
    seed_default_admin(db)
