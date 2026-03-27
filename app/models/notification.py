import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationType(str, enum.Enum):
    donation_received = "donation_received"
    campaign_created = "campaign_created"
    campaign_status_changed = "campaign_status_changed"
    general = "general"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("donations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType), nullable=False, default=NotificationType.general
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")  # noqa: F821
    donation: Mapped["Donation | None"] = relationship(  # noqa: F821
        "Donation", back_populates="notifications"
    )
    campaign: Mapped["Campaign | None"] = relationship(  # noqa: F821
        "Campaign", back_populates="notifications"
    )
