from pydantic import BaseModel


class PolicyOut(BaseModel):
    id: str
    classification: str
    min_score: int
    max_score: int
    require_alert: bool
    require_masking: bool
    require_watermark: bool
    require_footer: bool
    allow_printing: bool

    model_config = {"from_attributes": True}


class PolicyUpdate(BaseModel):
    min_score: int | None = None
    max_score: int | None = None
    require_alert: bool | None = None
    require_masking: bool | None = None
    require_watermark: bool | None = None
    require_footer: bool | None = None
    allow_printing: bool | None = None
