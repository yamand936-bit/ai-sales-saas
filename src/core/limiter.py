import logging
from src.core.config import settings
import redis

logger = logging.getLogger(__name__)

try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception as e:
    redis_client = None
    logger.error(f"Redis initialization failed: {e}")

def check_rate_limit(user_id: str, limit: int = 5, window: int = 10, block_time: int = 600) -> bool:
    """Returns True if user is under limit, False if blocked (429 Drop Logic)."""
    if not redis_client:
        return True # Fail open to prevent downtime if Redis goes down temporarily
        
    try:
        block_key = f"blocked:{user_id}"
        if redis_client.get(block_key):
            return False # Still serving the 10-minute penalty
            
        key = f"rate_limit:{user_id}"
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window)
            
        if current > limit:
            # Drop task and impose the 600s block time
            redis_client.setex(block_key, block_time, "1")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Rate Limiter Exception: {e}")
        return True
