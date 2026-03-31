from pydantic import BaseModel
from typing import Optional

class StoreCreate(BaseModel):
    name: str
    owner_name: str
    owner_email: str
    password: str
    plan_price: float = 0.0
    monthly_token_limit: int = 100000

class SystemSettingUpdate(BaseModel):
    key: str
    value: str
