"""
Updated request/response models for leads (replaces the original order schemas).
"""
import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: str
    confidence: float


class LeadOut(BaseModel):
    id: str
    created_at: datetime.datetime
    session_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    lead_type: str
    service_type: str | None = None
    home_size: str | None = None
    zip_code: str | None = None
    preferred_datetime: str | None = None
    notes: str | None = None
    status: str

    class Config:
        from_attributes = True


class TicketOut(BaseModel):
    id: str
    created_at: datetime.datetime
    session_id: str
    message: str
    status: str

    class Config:
        from_attributes = True
