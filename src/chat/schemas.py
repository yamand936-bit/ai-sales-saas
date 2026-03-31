from pydantic import BaseModel
from typing import Optional

class MessageCreate(BaseModel):
    message: str
