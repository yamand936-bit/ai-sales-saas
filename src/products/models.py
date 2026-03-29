from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from src.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"))
    name = Column(String, index=True, nullable=False)
    sku = Column(String, index=True, nullable=True)
    price = Column(Float)
    description = Column(String)
    image_url = Column(String, nullable=True)
    attributes = Column(String, nullable=True) # For size, color, etc.
    category = Column(String, index=True, nullable=True)
    type = Column(String, default="product") # "product" | "service"
    duration = Column(Integer, nullable=True) # minutes for service
    has_sizes = Column(Boolean, default=False)
    sizes = Column(String, nullable=True) # JSON string e.g. {"S": True, "M": False}
    is_active = Column(Boolean, default=True)
    is_service = Column(Boolean, default=False)
    booking_link = Column(String, nullable=True)
    quality_score = Column(Float, default=5.0) # Used for AI best-value ranking
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    store = relationship("Store", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")
