import json
import logging
import redis
from src.core.config import settings
from src.core.database import SessionLocal
from src.core.models import FeatureFlag

logger = logging.getLogger(__name__)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

class FeatureService:
    @staticmethod
    def is_enabled(key: str) -> bool:
        cache_key = f"feature:{key}"
        try:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached.lower() == 'true'
        except Exception as e:
            logger.warning(f"Redis cache error reading feature flag: {e}")

        # Fallback to DB
        db = SessionLocal()
        try:
            flag = db.query(FeatureFlag).filter_by(key=key).first()
            if flag:
                # Save to cache with 60 sec TTL
                try:
                    redis_client.setex(cache_key, 60, str(flag.enabled).lower())
                except Exception:
                    pass
                return flag.enabled
            return False
        except Exception as e:
            logger.error(f"Error reading feature flag from DB: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def toggle_feature(key: str) -> bool:
        db = SessionLocal()
        try:
            flag = db.query(FeatureFlag).filter_by(key=key).first()
            if flag:
                flag.enabled = not flag.enabled
                db.commit()
                # Invalid cache
                try:
                    redis_client.delete(f"feature:{key}")
                except Exception:
                    pass
                return flag.enabled
            return False
        finally:
            db.close()

    @staticmethod
    def initialize_defaults():
        defaults = [
            ("ai_system", "Core AI processing for incoming customer messages"),
            ("auto_followup", "Automated cron-based background customer retention"),
            ("broadcast", "Mass message broadcasting to all customers"),
            ("analytics_dashboard", "Advanced charts and data on merchant panel")
        ]
        db = SessionLocal()
        try:
            for key, desc in defaults:
                exists = db.query(FeatureFlag).filter_by(key=key).first()
                if not exists:
                    db.add(FeatureFlag(key=key, enabled=True, description=desc))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to initialize default feature flags: {e}")
            db.rollback()
        finally:
            db.close()
