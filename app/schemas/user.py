import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    wallet_address: str
    fcm_token: str | None = None
    username: str | None = None
    email: str | None = None

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet(cls, v: str) -> str:
        if not v.startswith("0x") or len(v) != 42:
            raise ValueError("wallet_address must be a valid 42-char Ethereum address")
        return v.lower()


class UserUpdate(BaseModel):
    fcm_token: str | None = None
    username: str | None = None
    email: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    wallet_address: str
    fcm_token: str | None
    username: str | None
    email: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
