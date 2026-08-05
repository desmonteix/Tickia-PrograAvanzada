from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import uuid
from .models import TicketState, HashState

# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    phone_number: str = Field(min_length=6)
    ref_code: Optional[str] = None

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_email_verified: bool
    is_kyc_verified: bool
    trust_score: int
    is_admin: bool
    has_access: bool
    referral_code: Optional[str] = None
    
    class Config:
        from_attributes = True

class WaitlistStatus(BaseModel):
    position: int
    referral_code: str
    referral_count: int
    has_access: bool

# --- Ticket Schemas ---
class TicketCreate(BaseModel):
    event_name: str = Field(..., min_length=3)
    event_date: datetime
    zone: str = Field(..., min_length=1)
    ticketing_company: str = Field(..., min_length=2)
    ticket_type: str = Field(..., min_length=2)
    price: float = Field(..., gt=0)

class TicketResponse(BaseModel):
    id: uuid.UUID
    event_name: str
    event_date: datetime
    zone: str
    ticketing_company: str
    ticket_type: str
    price: float
    estado: TicketState
    seller_id: uuid.UUID
    created_at: datetime
    boosted_until: Optional[datetime] = None
    
    # IMPORTANTE: Nunca devolver el qr_hash, ni la URL del qr_image aquí.
    # El buyer_id solo se expone a dueños o backend interno, pero por seguridad en lista general omitimos.
    
    class Config:
        from_attributes = True

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str
    
class TokenData(BaseModel):
    user_id: Optional[str] = None
