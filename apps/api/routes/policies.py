from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.policy import ClassificationPolicy
from apps.api.schemas.policy import PolicyOut, PolicyUpdate
from apps.api.security.auth import require_admin

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


@router.get("", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return db.query(ClassificationPolicy).order_by(ClassificationPolicy.min_score).all()


@router.patch("/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: str, payload: PolicyUpdate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    policy = db.get(ClassificationPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    data = payload.model_dump(exclude_unset=True)
    if "min_score" in data or "max_score" in data:
        new_min = data.get("min_score", policy.min_score)
        new_max = data.get("max_score", policy.max_score)
        if new_min > new_max:
            raise HTTPException(status_code=400, detail="min_score cannot exceed max_score")
    for k, v in data.items():
        setattr(policy, k, v)
    db.commit()
    db.refresh(policy)
    return policy
