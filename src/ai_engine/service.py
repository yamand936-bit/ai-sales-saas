import time
import logging
import json
from openai import OpenAI
from src.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_MODELS = {
    "gpt-4o": "gpt-4o-mini",
    "gpt-4o-mini": "gpt-3.5-turbo",
    "gpt-4": "gpt-3.5-turbo",
    "gemini-3.1-pro": "gemini-3.1-flash",
    "gemini-pro": "gemini-flash"
}

class AIEngineService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = "gpt-4o-mini"

    def is_configured(self) -> bool:
        return self.client is not None

    def _execute_with_retry(self, is_json=False, **kwargs) -> str:
        max_retries = 3
        delays = [2, 5, 10]
        current_model = kwargs.get("model", self.model)
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                is_capacity_err = "503" in err_str or "model_capacity_exhausted" in err_str or "timeout" in err_str or "connection" in err_str
                
                if not is_capacity_err and attempt == 0:
                    # Generic failure
                    logger.warning(f"[AI] Non-recoverable error detected: {e}")
                    pass
                
                # Check for specific retry delay headers if exposed by exception args
                wait_time = delays[attempt]
                if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = max(wait_time, int(retry_after))
                
                logger.warning(f"[AI] API Error (Attempt {attempt+1}/{max_retries}) | Model: {current_model} | Error: {e} | Retrying in {wait_time}s...")
                time.sleep(wait_time)
                
        # Switch to fallback model
        fallback_model = FALLBACK_MODELS.get(current_model, "gpt-3.5-turbo")
        logger.warning(f"[AI] All {max_retries} retries exhausted. Switching to FALLBACK model: {fallback_model}...")
        kwargs["model"] = fallback_model
        
        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"[AI] FAST-FAIL: Fallback model {fallback_model} failed! Final Error: {e}")
            safe_message = "⚠️ النظام مشغول حالياً، حاول مرة أخرى بعد لحظات | System is busy, please try again shortly"
            if is_json:
                return json.dumps({"reply": safe_message, "intent": "none", "entities": {}}, ensure_ascii=False)
            return safe_message

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        if not self.is_configured():
            return ""
        try:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=(filename, audio_bytes, "audio/ogg")
            )
            return transcript.text
        except Exception as e:
            logger.error(f"Whisper Transcription Error: {e}")
            return ""

    def generate_response(self, system_prompt: str, user_message: str, context: list = None, image_base64: str = None) -> str:
        from src.core.database import SessionLocal
        from src.core.models import SystemSetting
        
        db = SessionLocal()
        try:
            ai_status = db.query(SystemSetting).filter_by(key="ai_enabled").first()
            if ai_status and ai_status.value.lower() != "true":
                logger.warning("AI generation skipped: Globally disabled in SystemSettings")
                return "عذراً، نظام الذكاء الاصطناعي موقوف مؤقتاً من قبل الإدارة."
        finally:
            db.close()

        if not self.is_configured():
            logger.warning("OpenAI not configured.")
            return "عذراً، نظام الذكاء الاصطناعي قيد الصيانة."

        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.extend(context)
            
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message or "يوجد صورة مرفقة من العميل، قم بتحليلها بصرياً وابحث عن ساعة مطابقة أو مشابهة جداً في المخزون واذكر سعرها ومميزاتها."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": user_message})

        try:
            return self._execute_with_retry(
                is_json=False,
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=600
            )
        except Exception as e:
            logger.error(f"UNHANDLED AI Generation Error: {e}")
            return "حدث خطأ غير متوقع في الذكاء الاصطناعي."

    def generate_json_response(self, system_prompt: str, user_message: str, context: list = None, image_base64: str = None) -> str:
        from src.core.database import SessionLocal
        from src.core.models import SystemSetting
        
        db = SessionLocal()
        try:
            ai_status = db.query(SystemSetting).filter_by(key="ai_enabled").first()
            if ai_status and ai_status.value.lower() != "true":
                logger.warning("AI generation skipped: Globally disabled in SystemSettings")
                return '{"reply": "النظام معلق حالياً من قبل الإدارة للترقية.", "intent": "none", "entities": {}}'
        finally:
            db.close()
            
        if not self.is_configured():
            logger.warning("OpenAI not configured.")
            return '{"reply": "عذراً، نظام الذكاء الاصطناعي قيد الصيانة (يرجى إضافة مفتاح OpenAI).", "intent": "none", "entities": {}}'

        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.extend(context)
            
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message or "يوجد صورة مرفقة من العميل، حللها."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": user_message})

        try:
            return self._execute_with_retry(
                is_json=True,
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=600
            )
        except Exception as e:
            logger.error(f"UNHANDLED AI JSON Gen Error: {e}")
            return '{"reply": "حدث خطأ غير متوقع في الذكاء الاصطناعي.", "intent": "none", "entities": {}}'

ai_engine = AIEngineService()
