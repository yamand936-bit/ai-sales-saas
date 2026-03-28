import json
import logging
import redis
from src.core.config import settings

logger = logging.getLogger(__name__)

# Singleton redis connection for pub/sub
try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception as e:
    redis_client = None
    logger.error(f"Redis Pub/Sub init failed: {e}")

def publish_event(store_id: int, event_type: str, data: dict):
    if not redis_client:
        return
    try:
        payload = json.dumps({"type": event_type, "store_id": store_id, "data": data}, ensure_ascii=False)
        redis_client.publish(f"store_{store_id}", payload)
        logger.info(f"Published event {event_type} to store_{store_id}")
    except Exception as e:
        logger.error(f"Pub/Sub Publish Error: {e}")
