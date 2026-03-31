import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set. Production requires a PostgreSQL database url.")
    if "sqlite" in DATABASE_URL:
        raise ValueError("SQLite is no longer supported. Please use a PostgreSQL connection string in DATABASE_URL.")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SUPERADMIN_PASSWORD: str = os.getenv("SUPERADMIN_PASSWORD")
    if not SUPERADMIN_PASSWORD:
        raise ValueError("SUPERADMIN_PASSWORD not set")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    
    # MULTI-PROVIDER CONFIGURATION
    AI_PROVIDERS = {
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "is_active": bool(os.getenv("OPENAI_API_KEY", "")),
            "cost_tier": 2 # Medium cost
        },
        "gemini": {
            "api_key": os.getenv("GEMINI_API_KEY", ""),
            "is_active": bool(os.getenv("GEMINI_API_KEY", "")),
            "cost_tier": 1 # Cheaper cost
        }
    }

settings = Settings()
