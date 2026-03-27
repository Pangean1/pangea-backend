import uuid
from datetime import datetime

from pydantic import BaseModel


class DonationResponse(BaseModel):
    id: uuid.UUID
    tx_hash: str
    log_index: int
    campaign_id: uuid.UUID | None
    on_chain_campaign_id: int
    donor_address: str
    recipient_address: str
    token_address: str
    amount_wei: str
    message: str
    block_timestamp: datetime
    block_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DonationListResponse(BaseModel):
    items: list[DonationResponse]
    total: int
