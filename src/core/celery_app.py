import os
import logging
from src.core.config import settings

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    Celery = None
    CELERY_AVAILABLE = False

redis_available = False
if CELERY_AVAILABLE:
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        redis_available = True
    except Exception:
        redis_available = False

if CELERY_AVAILABLE and redis_available:
    celery = Celery(
        "ai_sales_tasks",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=['src.chat.tasks']
    )
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True
    )
else:
    print("Running in DEV mode (no Celery, no Redis)")
    class DummyCelery:
        class Conf:
            def update(self, **kwargs):
                pass
        
        def __init__(self):
            self.conf = self.Conf()
            
        def task(self, *args, **kwargs):
            def decorator(func):
                def delay_wrapper(*a, **kw):
                    try:
                        if kwargs.get('bind'):
                            class DummyTask:
                                def retry(self, exc=None, countdown=0):
                                    logger.error(f"Task {func.__name__} retry requested: {exc}")
                            return func(DummyTask(), *a, **kw)
                        return func(*a, **kw)
                    except Exception as e:
                        logger.error(f"Sync execution failed: {e}")
                func.delay = delay_wrapper
                return func
            return decorator
            
    celery = DummyCelery()
