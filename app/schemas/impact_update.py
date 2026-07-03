import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.impact_update import MediaType


class ImpactUpdateResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    message: str
    media_url: str | None
    media_type: MediaType | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImpactUpdateListResponse(BaseModel):
    items: list[ImpactUpdateResponse]
    total: int
