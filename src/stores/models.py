from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from src.core.database import Base
from sqlalchemy.types import TypeDecorator
from cryptography.fernet import Fernet
from src.core.config import settings

if not settings.ENCRYPTION_KEY:
    raise ValueError("CRITICAL: ENCRYPTION_KEY is missing from environment variables. The application cannot start securely.")

try:
    fernet = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception as e:
    raise ValueError(f"CRITICAL: Invalid ENCRYPTION_KEY format. Must be a 32 URL-safe base64-encoded bytes. Error: {e}")

class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and fernet:
            return fernet.encrypt(value.encode()).decode()
        return value

    def process_result_value(self, value, dialect):
        if value is not None and fernet:
            if value == "":
                return ""
            try:
                return fernet.decrypt(value.encode()).decode()
            except Exception:
                return value
        return value

class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price_usd = Column(Float, default=0)
    monthly_token_limit = Column(Integer, default=100000)
    features = Column(Text, nullable=True)

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    telegram_token = Column(EncryptedString, unique=True, index=True)
    language = Column(String, default="ar")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    password_hash = Column(String, nullable=True) # Phase 7 Auth
    
    # --- Enterprise Fields ---
    owner_name = Column(String, nullable=True)
    owner_phone = Column(String, nullable=True)
    owner_email = Column(String, nullable=True)
    country = Column(String, nullable=True)
    has_branches = Column(Boolean, default=False)
    branch_names = Column(String, nullable=True)
    status = Column(String, default="active") # active, suspended, expired, blocked
    currency = Column(String, default="USD")
    features = Column(Text, default='{"whatsapp": false, "instagram": false, "voice": false, "advanced_ai": false}') # JSON
    ai_enabled = Column(Boolean, default=True) # True = AI Active, False = AI Muted
    
    # --- Billing & Monetization (Phase 8) ---
    plan_price = Column(Float, default=0.0)
    billing_cycle = Column(String, default="monthly") # monthly, yearly
    last_payment_date = Column(DateTime, nullable=True)
    next_billing_date = Column(DateTime, nullable=True)
    payment_status = Column(String, default="paid") # paid, pending, overdue
    monthly_token_limit = Column(Integer, default=100000)
    
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    subscription_status = Column(String, default="active")
    
    # Legacy Fields (To be migrated/removed if needed but kept for safety)
    subscription_fee = Column(Float, default=0.0)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True) 
    subscription_end_date = Column(DateTime, nullable=True)
    
    # --- AI Behavior Settings ---
    ai_tone = Column(String, default="احترافي وراقٍ")
    sales_strategy = Column(String, default="مساعد مباشر ومستشار مبيعات")
    ai_mode = Column(String, default="sales")
    policy = Column(String, nullable=True)
    
    # --- Multi-Platform Tokens ---
    whatsapp_token = Column(EncryptedString, nullable=True)
    instagram_token = Column(EncryptedString, nullable=True)
    
    # --- Payment Info ---
    bank_account_number = Column(String, nullable=True)
    bank_account_name = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="store", foreign_keys="[User.store_id]", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="store", cascade="all, delete-orphan")
    plan = relationship("Plan")

class AdminLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, nullable=True) # Superadmin store_id, usually 1
    action = Column(String, nullable=False)
    target_store_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
