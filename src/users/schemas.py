from pydantic import BaseModel
from typing import Optional

class UserRead(BaseModel):
    id: int
    first_name: str
    telegram_id: Optional[str] = None
    class Config:
        from_attributes = True
