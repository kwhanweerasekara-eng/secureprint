from datetime import datetime

from pydantic import BaseModel


class ApiTokenOut(BaseModel):
    id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool

    model_config = {"from_attributes": True}


class ApiTokenCreate(BaseModel):
    name: str


class ApiTokenCreated(BaseModel):
    id: str
    name: str
    token: str  # shown once - never retrievable again
    token_prefix: str
    created_at: datetime
