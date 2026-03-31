from pydantic import BaseModel
from typing import Optional

class OrderRead(BaseModel):
    id: int
    total: float
    status: str
    class Config:
        from_attributes = True
