import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./saas.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SUPERADMIN_PASSWORD: str = os.getenv("SUPERADMIN_PASSWORD", "superadmin123")
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
