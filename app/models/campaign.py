import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, BigInteger, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    # on_chain_id mirrors the uint256 campaign ID from the smart contract
    on_chain_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    recipient_address: Mapped[str] = mapped_column(
        String(42), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # total_raised_wei: stored as string to avoid integer overflow for large uint256 values
    total_raised_wei: Mapped[str] = mapped_column(
        String(78), nullable=False, default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    donations: Mapped[list["Donation"]] = relationship(  # noqa: F821
        "Donation", back_populates="campaign", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="campaign"
    )
