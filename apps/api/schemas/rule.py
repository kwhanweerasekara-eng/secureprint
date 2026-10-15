from pydantic import BaseModel


class RuleOut(BaseModel):
    id: str
    name: str
    category: str
    pattern: str
    description: str
    priority: int
    requires_keyword_context: bool
    context_keywords: str
    enabled: bool

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    name: str
    category: str
    pattern: str
    description: str = ""
    priority: int = 50
    requires_keyword_context: bool = False
    context_keywords: str = ""
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    pattern: str | None = None
    description: str | None = None
    priority: int | None = None
    requires_keyword_context: bool | None = None
    context_keywords: str | None = None
    enabled: bool | None = None


class KeywordOut(BaseModel):
    id: str
    category: str
    term: str
    enabled: bool

    model_config = {"from_attributes": True}


class KeywordCreate(BaseModel):
    category: str
    term: str
    enabled: bool = True


class RiskWeightOut(BaseModel):
    id: str
    category: str
    label: str
    weight: int
    enabled: bool

    model_config = {"from_attributes": True}


class RiskWeightUpdate(BaseModel):
    weight: int | None = None
    enabled: bool | None = None
    label: str | None = None
