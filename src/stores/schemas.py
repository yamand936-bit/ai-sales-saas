from pydantic import BaseModel
from typing import Optional

class StoreUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    plan_price: Optional[float] = None
    billing_cycle: Optional[str] = None
    monthly_token_limit: Optional[int] = None
    payment_status: Optional[str] = None
    extend_days: Optional[int] = None
    telegram_token: Optional[str] = None
    whatsapp_token: Optional[str] = None
    instagram_token: Optional[str] = None
    feat_whatsapp: Optional[str] = None
    feat_instagram: Optional[str] = None
    feat_voice: Optional[str] = None
    feat_advanced_ai: Optional[str] = None
