import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.rule import DetectionRule, Keyword, RiskWeight
from apps.api.schemas.rule import (
    KeywordCreate,
    KeywordOut,
    RiskWeightOut,
    RiskWeightUpdate,
    RuleCreate,
    RuleOut,
    RuleUpdate,
)
from apps.api.security.auth import require_admin

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


def _validate_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"Invalid regular expression: {exc}")


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return db.query(DetectionRule).order_by(DetectionRule.category, DetectionRule.name).all()


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    _validate_pattern(payload.pattern)
    rule = DetectionRule(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: str, payload: RuleUpdate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    rule = db.get(DetectionRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    data = payload.model_dump(exclude_unset=True)
    if "pattern" in data:
        _validate_pattern(data["pattern"])
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    rule = db.get(DetectionRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


@router.get("/keywords/all", response_model=list[KeywordOut])
def list_keywords(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return db.query(Keyword).order_by(Keyword.category, Keyword.term).all()


@router.post("/keywords", response_model=KeywordOut, status_code=201)
def create_keyword(payload: KeywordCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    kw = Keyword(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: str, enabled: bool, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    kw = db.get(Keyword, keyword_id)
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    kw.enabled = enabled
    db.commit()
    db.refresh(kw)
    return kw


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(keyword_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    kw = db.get(Keyword, keyword_id)
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    db.delete(kw)
    db.commit()


@router.get("/weights/all", response_model=list[RiskWeightOut])
def list_weights(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return db.query(RiskWeight).order_by(RiskWeight.category).all()


@router.patch("/weights/{weight_id}", response_model=RiskWeightOut)
def update_weight(weight_id: str, payload: RiskWeightUpdate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    w = db.get(RiskWeight, weight_id)
    if not w:
        raise HTTPException(status_code=404, detail="Risk weight not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return w
