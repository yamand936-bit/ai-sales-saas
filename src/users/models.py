from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from src.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"))
    phone = Column(String, index=True, nullable=True)
    telegram_id = Column(String, index=True, nullable=True)
    first_name = Column(String)
    preferences = Column(String, nullable=True)
    conversation_state = Column(String, default="idle")
    active_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Monetization fields
    plan = Column(String, default="free") 
    messages_used = Column(Integer, default=0)
    messages_limit = Column(Integer, nullable=True) 

    # Relationships
    store = relationship("Store", back_populates="users", foreign_keys="[User.store_id]")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete")
