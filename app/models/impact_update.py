import uuid
import enum
from datetime import datetime

from sqlalchemy import DateTime, func, Text, String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MediaType(str, enum.Enum):
    image = "image"
    video = "video"


class ImpactUpdate(Base):
    __tablename__ = "impact_updates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[MediaType | None] = mapped_column(SAEnum(MediaType), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(  # noqa: F821
        "Campaign", back_populates="impact_updates"
    )
