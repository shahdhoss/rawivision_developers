from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional


class SubscriptionCreate(BaseModel):
    tenant_id: UUID
    plan_id: str
    subscription_type: str  # "monthly" | "annual"


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subscription_id: UUID
    state: str
    trial_ends_at: Optional[datetime]


class SubscriptionStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subscription_id: UUID
    state: str


class CheckInRequest(BaseModel):
    installation_uuid: UUID

class CheckInResponse(BaseModel):
    status: str          # "ok" | "suspended" | "canceled" | "expired"
    message: Optional[str] = None
    attendance: Optional[bool] = None
    search: Optional[bool] = None
    summarization: Optional[bool] = None