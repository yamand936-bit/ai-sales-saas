import logging
from openai import OpenAI
from src.core.config import settings

logger = logging.getLogger(__name__)

class AIEngineService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = "gpt-4o-mini"

    def is_configured(self) -> bool:
        return self.client is not None

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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=600
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Generation Error: {e}")
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=600
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI JSON Gen Error: {e}")
            return '{"reply": "حدث خطأ غير متوقع في الذكاء الاصطناعي.", "intent": "none", "entities": {}}'

ai_engine = AIEngineService()
