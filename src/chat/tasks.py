import logging
from src.core.celery_app import celery
from src.ai_engine.decision import DecisionEngine

logger = logging.getLogger(__name__)
decision_engine = DecisionEngine()

# Event System / Observability Logging Wrapper
def _log_event(platform, token, status, meta=""):
    logger.info(f"[EVENT] Platform: {platform} | Token: {token[:5]}... | Status: {status} | Meta: {meta}")

def check_store_limits(platform: str, token: str):
    from src.core.database import SessionLocal
    from src.stores.models import Store
    from src.chat.models import AILog
    from sqlalchemy import func
    from datetime import datetime
    
    db = SessionLocal()
    try:
        store = None
        for s in db.query(Store).filter(Store.status == 'active').all():
            if platform == "telegram" and getattr(s, 'telegram_token', None) == token: store = s; break
            elif platform == "whatsapp" and getattr(s, 'whatsapp_token', None) == token: store = s; break
            elif platform == "instagram" and getattr(s, 'instagram_token', None) == token: store = s; break

        if not store: return False, "Store Not Found"

        # 1. Status Check
        if store.status != 'active':
            return False, f"Store is {store.status}"

        # 2. Expiry Check
        if store.next_billing_date and store.next_billing_date < datetime.utcnow():
            store.status = 'expired'
            store.payment_status = 'overdue'
            db.commit()
            return False, "Store Subscription Expired"

        # 3. Quota Enforcement
        current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tokens_used = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens))\
                        .filter(AILog.store_id == store.id, AILog.created_at >= current_month).scalar() or 0
                        
        if store.monthly_token_limit and store.monthly_token_limit > 0:
            if tokens_used >= store.monthly_token_limit:
                return False, f"Token Quota Exceeded ({tokens_used}/{store.monthly_token_limit})"
        
        return True, "OK"
    finally:
        db.close()

@celery.task(name="process_telegram_task", bind=True, max_retries=3)
def process_telegram_webhook(self, token: str, update: dict):
    print("TASK START")
    try:
        _log_event("telegram", token, "Message Received")
        allowed, reason = check_store_limits("telegram", token)
        if not allowed:
            _log_event("telegram", token, "Rejected", f"Quota/Limits: {reason}")
            return
            
        message = update.get("message", {})
        msg_id = str(message.get("message_id", ""))
        text = message.get("text", "")
        
        # Audio extraction proxy (simplified for unified flow)
        if "voice" in message:
            text = "[VOICE NOTE RECEIVED]"

        user_id = message.get("from", {}).get("id")
        first_name = message.get("from", {}).get("first_name", "User")
        
        from src.core.limiter import check_rate_limit
        if not check_rate_limit(f"tg_{user_id}"):
            _log_event("telegram", token, "Rate Limited")
            return
            
        reply = decision_engine.process_message("telegram", token, user_id, first_name, text, msg_id=msg_id)
        if reply:
            from src.chat.service import send_telegram_msg
            send_telegram_msg(token, str(user_id), reply)
            _log_event("telegram", token, "Reply Generated")
    except Exception as e:
        _log_event("telegram", token, "Error", str(e))
        self.retry(exc=e, countdown=5)
    finally:
        print("TASK END")

@celery.task(name="process_whatsapp_task", bind=True, max_retries=3)
def process_whatsapp_webhook(self, token: str, update: dict):
    try:
        _log_event("whatsapp", token, "Message Received")
        allowed, reason = check_store_limits("whatsapp", token)
        if not allowed:
            _log_event("whatsapp", token, "Rejected", f"Quota/Limits: {reason}")
            return
            
        entry = update.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages: return
        msg = messages[0]
        msg_id = msg.get("id", "")
        text = msg.get("text", {}).get("body", "")
        user_phone = msg.get("from")
        first_name = "WA User"
        
        from src.core.limiter import check_rate_limit
        if not check_rate_limit(f"wa_{user_phone}"):
            _log_event("whatsapp", token, "Rate Limited")
            return
            
        reply = decision_engine.process_message("whatsapp", token, user_phone, first_name, text, msg_id=msg_id)
        if reply:
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            if phone_number_id:
                import requests
                url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"messaging_product": "whatsapp", "to": user_phone, "type": "text", "text": {"body": reply}}
                res = requests.post(url, headers=headers, json=payload)
                if not res.ok:
                    _log_event("whatsapp", token, "Send Error", res.text)
            _log_event("whatsapp", token, "Reply Generated")
    except Exception as e:
        _log_event("whatsapp", token, "Error", str(e))
        self.retry(exc=e, countdown=5)

@celery.task(name="process_instagram_task", bind=True, max_retries=3)
def process_instagram_webhook(self, token: str, update: dict):
    try:
        _log_event("instagram", token, "Message Received")
        allowed, reason = check_store_limits("instagram", token)
        if not allowed:
            _log_event("instagram", token, "Rejected", f"Quota/Limits: {reason}")
            return
            
        entry = update.get("entry", [{}])[0]
        messaging_events = entry.get("messaging", [])
        if not messaging_events: return
        msg_ev = messaging_events[0]
        msg_id = msg_ev.get("message", {}).get("mid", "")
        sender_id = msg_ev.get("sender", {}).get("id")
        text = msg_ev.get("message", {}).get("text", "")
        
        from src.core.limiter import check_rate_limit
        if not check_rate_limit(f"ig_{sender_id}"):
            _log_event("instagram", token, "Rate Limited")
            return
            
        reply = decision_engine.process_message("instagram", token, sender_id, "IG User", text, msg_id=msg_id)
        if reply:
            import requests
            url = "https://graph.facebook.com/v17.0/me/messages"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {"recipient": {"id": sender_id}, "message": {"text": reply}}
            res = requests.post(url, headers=headers, json=payload)
            if not res.ok:
                _log_event("instagram", token, "Send Error", res.text)
            _log_event("instagram", token, "Reply Generated")
    except Exception as e:
        _log_event("instagram", token, "Error", str(e))
        self.retry(exc=e, countdown=5)

