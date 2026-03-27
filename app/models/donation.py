import uuid
from datetime import datetime

from sqlalchemy import String, BigInteger, DateTime, func, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    # Ethereum transaction hash — uniquely identifies this on-chain event
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, index=True, nullable=False)
    # Log index within the transaction (used together with tx_hash for dedup)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # FK to our local campaigns table
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # on_chain campaign ID preserved for reference even if local campaign row is missing
    on_chain_campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    donor_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    token_address: Mapped[str] = mapped_column(String(42), nullable=False)

    # Amount stored as string to safely represent uint256
    amount_wei: Mapped[str] = mapped_column(String(78), nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # block_timestamp from the on-chain event
    block_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign | None"] = relationship(  # noqa: F821
        "Campaign", back_populates="donations"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="donation"
    )
