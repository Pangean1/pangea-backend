import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.impact_update import MediaType


class CampaignResponse(BaseModel):
    id: uuid.UUID
    on_chain_id: int
    recipient_address: str
    name: str
    description: str
    active: bool
    total_raised_wei: str
    goal_wei: str
    media_url: str | None
    media_type: MediaType | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int


class CampaignUpdateRequest(BaseModel):
    goal_usd: str | None = None
    deadline: datetime | None = None


class CampaignStatusRequest(BaseModel):
    active: bool
