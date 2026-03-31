from pydantic import BaseModel
from typing import Optional

class AIConfigUpdate(BaseModel):
    ai_mode: str = "off"
    ai_tone: str = "friendly"
    policy: str = ""
