import uuid
from datetime import datetime

from pydantic import BaseModel


class CampaignResponse(BaseModel):
    id: uuid.UUID
    on_chain_id: int
    recipient_address: str
    name: str
    description: str
    active: bool
    total_raised_wei: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
