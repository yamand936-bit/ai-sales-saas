from sqlalchemy import Column, Integer, String, Boolean
from src.core.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)

class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    description = Column(String, nullable=True)
