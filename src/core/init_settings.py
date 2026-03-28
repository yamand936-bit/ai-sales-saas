from src.core.database import SessionLocal
from src.core.models import SystemSetting

def init_settings():
    db = SessionLocal()
    defaults = {
        "free_limit": "100",
        "basic_limit": "1000",
        "pro_limit": "10000",
        "ai_enabled": "true"
    }

    for key, value in defaults.items():
        existing = db.query(SystemSetting).filter_by(key=key).first()
        if not existing:
            db.add(SystemSetting(key=key, value=value))

    db.commit()
    db.close()
