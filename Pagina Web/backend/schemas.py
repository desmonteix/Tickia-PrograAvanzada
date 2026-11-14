from datetime import datetime, timezone
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, field_serializer
from .models import TicketState


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone_number: str = Field(min_length=6, max_length=25)
    referral_code: Optional[str] = Field(default=None, pattern=r'^[A-Za-z0-9_-]{6,64}$')

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()

    @field_validator("password")
    @classmethod
    def limit_password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no debe superar 72 bytes UTF-8")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_email_verified: bool
    is_kyc_verified: bool
    trust_score: int
    rating: float
    warning_count: int
    is_admin: bool


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_name: str
    event_date: datetime
    event_end_date: Optional[datetime] = None
    seller_rating: float
    zone: str
    ticketing_company: str
    ticket_type: str
    is_renominated: bool
    price: float
    commission_rate: float
    estado: TicketState
    seller_id: uuid.UUID
    created_at: datetime
    boosted_until: Optional[datetime] = None

    @field_serializer("event_date", "event_end_date", "created_at", "boosted_until")
    def serialize_utc(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Token(BaseModel):
    access_token: str
    token_type: str
