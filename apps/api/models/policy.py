from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.base import Base
from apps.api.models.enums import Classification


class ClassificationPolicy(Base):
    __tablename__ = "classification_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classification: Mapped[Classification] = mapped_column(Enum(Classification), unique=True, nullable=False)
    min_score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    require_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    require_masking: Mapped[bool] = mapped_column(Boolean, default=False)
    require_watermark: Mapped[bool] = mapped_column(Boolean, default=False)
    require_footer: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_printing: Mapped[bool] = mapped_column(Boolean, default=True)
