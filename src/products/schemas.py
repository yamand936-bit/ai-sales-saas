from pydantic import BaseModel
from typing import Optional

class ProductCreate(BaseModel):
    name: str
    price: float = 0.0
    description: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    is_service: bool = False
    booking_link: Optional[str] = None
    type: str = "product"
    duration: Optional[int] = None

class ProductRead(ProductCreate):
    id: int
    store_id: int
    class Config:
        from_attributes = True
