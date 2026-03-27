import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    donation_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    type: NotificationType
    title: str
    body: str
    is_read: bool
    is_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}
