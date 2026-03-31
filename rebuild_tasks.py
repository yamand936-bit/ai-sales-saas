import re

tasks_path = 'C:/Users/yaman/.gemini/antigravity/playground/ai-sales-saas/src/chat/tasks.py'
with open(tasks_path, 'r', encoding='utf-8') as f:
    code = f.read()

# Add imports for AIRetryException and Retry safely
if "AIRetryException" not in code:
    code = code.replace("from src.ai_engine.decision import DecisionEngine", 
        "from src.ai_engine.decision import DecisionEngine\nfrom src.ai_engine.service import AIRetryException\nfrom celery.exceptions import Retry")
elif "from celery.exceptions import Retry" not in code:
    code = code.replace("from src.ai_engine.service import AIRetryException", "from src.ai_engine.service import AIRetryException\nfrom celery.exceptions import Retry")

# Telegram Refactor
tg_except_old = """    except Exception as e:
        _log_event("telegram", token, "Error", str(e))
        self.retry(exc=e, countdown=5)
    finally:"""
tg_except_new = """    except AIRetryException as e:
        _log_event("telegram", token, "AIRetry", str(e))
        raise self.retry(exc=e, countdown=getattr(e, 'retry_after', 10), max_retries=1)
    except Exception as e:
        if isinstance(e, Retry): raise
        _log_event("telegram", token, "Fatal Error", str(e))
        try:
            from src.chat.service import send_telegram_msg
            send_telegram_msg(token, str(user_id), "⚠️ النظام مشغول حالياً، يرجى المحاولة بعد لحظات | System is busy, please try again shortly")
        except:
            pass
    finally:"""
code = code.replace(tg_except_old, tg_except_new)

# WhatsApp Refactor
wa_except_old = """    except Exception as e:
        _log_event("whatsapp", token, "Error", str(e))
        self.retry(exc=e, countdown=5)"""
wa_except_new = """    except AIRetryException as e:
        _log_event("whatsapp", token, "AIRetry", str(e))
        raise self.retry(exc=e, countdown=getattr(e, 'retry_after', 10), max_retries=1)
    except Exception as e:
        if isinstance(e, Retry): raise
        _log_event("whatsapp", token, "Fatal Error", str(e))
        try:
            phone_number_id = value.get("metadata", {}).get("phone_number_id") if 'value' in locals() else None
            user_phone = msg.get("from") if 'msg' in locals() else None
            if phone_number_id and user_phone:
                import requests
                url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"messaging_product": "whatsapp", "to": user_phone, "type": "text", "text": {"body": "⚠️ النظام مشغول حالياً، يرجى المحاولة بعد لحظات | System is busy, please try again shortly"}}
                requests.post(url, headers=headers, json=payload)
        except:
            pass"""
code = code.replace(wa_except_old, wa_except_new)

# Instagram Refactor
ig_except_old = """    except Exception as e:
        _log_event("instagram", token, "Error", str(e))
        self.retry(exc=e, countdown=5)"""
ig_except_new = """    except AIRetryException as e:
        _log_event("instagram", token, "AIRetry", str(e))
        raise self.retry(exc=e, countdown=getattr(e, 'retry_after', 10), max_retries=1)
    except Exception as e:
        if isinstance(e, Retry): raise
        _log_event("instagram", token, "Fatal Error", str(e))
        try:
            sender_id = msg_ev.get("sender", {}).get("id") if 'msg_ev' in locals() else None
            if sender_id:
                import requests
                url = "https://graph.facebook.com/v17.0/me/messages"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"recipient": {"id": sender_id}, "message": {"text": "⚠️ النظام مشغول حالياً، يرجى المحاولة بعد لحظات | System is busy, please try again shortly"}}
                requests.post(url, headers=headers, json=payload)
        except:
            pass"""
code = code.replace(ig_except_old, ig_except_new)


with open(tasks_path, 'w', encoding='utf-8') as f:
    f.write(code)

print("Tasks successfully modified.")
