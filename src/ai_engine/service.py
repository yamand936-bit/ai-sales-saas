import time
import logging
import json
import requests
import hashlib
from abc import ABC, abstractmethod
from openai import OpenAI
from src.core.config import settings

logger = logging.getLogger(__name__)

class AIRetryException(Exception):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after

# ==========================================
# PROVIDER ADAPTER LAYER
# ==========================================
class BaseProvider(ABC):
    def __init__(self, name: str, cost_tier: int):
        self.name = name
        self.cost_tier = cost_tier

    @abstractmethod
    def is_configured(self) -> bool: pass

    @abstractmethod
    def generate(self, model: str, messages: list, is_json: bool, **kwargs) -> str: pass

class OpenAIProvider(BaseProvider):
    def __init__(self):
        super().__init__("openai", settings.AI_PROVIDERS["openai"]["cost_tier"])
        self.api_key = settings.AI_PROVIDERS["openai"].get("api_key")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def is_configured(self) -> bool:
        return self.client is not None

    def generate(self, model: str, messages: list, is_json: bool, **kwargs) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 600),
            "timeout": 15.0
        }
        if is_json:
            payload["response_format"] = {"type": "json_object"}
            
        res = self.client.chat.completions.create(**payload)
        return res.choices[0].message.content

class GeminiProvider(BaseProvider):
    def __init__(self):
        super().__init__("gemini", settings.AI_PROVIDERS["gemini"]["cost_tier"])
        self.api_key = settings.AI_PROVIDERS["gemini"].get("api_key")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _convert_messages(self, messages: list) -> tuple:
        system_text = ""
        contents = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_text += str(content) + " "
                continue
                
            gemini_role = "user" if role == "user" else "model"
            
            # Text Only mode
            if isinstance(content, list):
                # Handle Image Extraction (Simplified for Gemini fallback, dropping image if any)
                text_parts = [c["text"] for c in content if c["type"] == "text"]
                content_str = " ".join(text_parts)
            else:
                content_str = str(content)
                
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content_str}]
            })
            
        return system_text.strip(), contents

    def generate(self, model: str, messages: list, is_json: bool, **kwargs) -> str:
        system_instructions, contents = self._convert_messages(messages)
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        
        payload = {"contents": contents}
        if system_instructions:
            payload["system_instruction"] = {"parts": [{"text": system_instructions}]}
            
        payload["generationConfig"] = {
            "temperature": kwargs.get("temperature", 0.7),
            "maxOutputTokens": kwargs.get("max_tokens", 600)
        }
        if is_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            
        res = requests.post(url, json=payload, timeout=15.0)
        
        if not res.ok:
            raise Exception(f"Gemini API Error {res.status_code}: {res.text}")
            
        data = res.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except:
            raise Exception(f"Gemini malformed response: {data}")

# ==========================================
# INTELLIGENT ROUTER LAYER
# ==========================================
class AIRouter:
    def __init__(self):
        self.providers = {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider()
        }
        import redis
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.redis_client.ping()
        except:
            self.redis_client = None

    def _get_cache(self, messages: list):
        if not self.redis_client: return None
        # Only cache short user queries
        last_msg = str(messages[-1]["content"]) if messages else ""
        if len(last_msg) > 100: return None
        
        h = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        return self.redis_client.get(f"ai_cache:{h}")

    def _set_cache(self, messages: list, response: str):
        if not self.redis_client: return
        last_msg = str(messages[-1]["content"]) if messages else ""
        if len(last_msg) > 100: return
        
        h = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        self.redis_client.setex(f"ai_cache:{h}", 1800, response) # 30 mins ttl

    def _record_metric(self, provider: str, metric: str):
        if not self.redis_client: return
        try:
            self.redis_client.incr(f"ai:{metric}")
            self.redis_client.incr(f"ai:{provider}:{metric}")
        except: pass

    def _record_failure(self, provider: str):
        if not self.redis_client: return
        try:
            key = f"failure_streak:{provider}"
            self.redis_client.rpush(key, str(time.time()))
            self.redis_client.expire(key, 60)
            self._record_metric(provider, "failure")
        except: pass

    def _is_degraded(self, provider: str) -> bool:
        if not self.redis_client: return False
        try:
            count = self.redis_client.llen(f"failure_streak:{provider}")
            return count >= 3
        except: return False

    def select_best_provider(self, is_complex: bool, is_downgraded: bool) -> tuple:
        active = [p for p in self.providers.values() if p.is_configured() and not self._is_degraded(p.name)]
        
        if not active:
            raise AIRetryException("All providers are currently degraded or unconfigured", retry_after=10)
            
        # Cost-aware Routing
        active.sort(key=lambda x: x.cost_tier)
        
        if is_downgraded:
            # Force cheapest
            best = active[0]
        else:
            # High complexity -> more capable usually means higher cost tier (naive heuristic)
            if is_complex and len(active) > 1:
                active.sort(key=lambda x: x.cost_tier, reverse=True) # more expensive = more complex
            best = active[0]
            
        model_name = "gpt-4o" if (best.name == "openai" and is_complex and not is_downgraded) else "gpt-4o-mini"
        if best.name == "gemini":
            model_name = "gemini-1.5-pro" if (is_complex and not is_downgraded) else "gemini-1.5-flash"
            
        return best, model_name

    def route_request(self, messages: list, is_json: bool, is_complex: bool, is_downgraded: bool, **kwargs) -> str:
        # Caching Layer Check
        cached = self._get_cache(messages)
        if cached:
            self._record_metric("cache", "hit")
            return cached

        best_provider, target_model = self.select_best_provider(is_complex, is_downgraded)
        
        max_retries = 3
        delays = [2, 5, 10]
        current_provider = best_provider
        
        for attempt in range(max_retries):
            try:
                res = current_provider.generate(target_model, messages, is_json, **kwargs)
                logger.info(f"[AI SUCCESS] Provider {current_provider.name} | Model {target_model}")
                self._record_metric(current_provider.name, "success")
                self._set_cache(messages, res)
                return res
            except Exception as e:
                err_str = str(e).lower()
                is_fatal = "invalid_api_key" in err_str or "401" in err_str or "unauthorized" in err_str
                
                self._record_failure(current_provider.name)
                
                if is_fatal:
                    logger.error(f"[AI FAILURE] Fatal Auth Error on {current_provider.name}. Aborting.")
                    raise e
                    
                logger.warning(f"[AI RETRY] Attempt {attempt+1}/{max_retries} failed on {current_provider.name}: {e}")
                self._record_metric(current_provider.name, "retry")
                time.sleep(delays[attempt])
                
        # Total exhaustion of targeted provider -> Fallback to next provider
        all_providers = [p for p in self.providers.values() if p.is_configured()]
        fallback_providers = [p for p in all_providers if p.name != current_provider.name and not self._is_degraded(p.name)]
        
        if fallback_providers:
            fallback = fallback_providers[0]
            fb_model = "gemini-1.5-flash" if fallback.name == "gemini" else "gpt-3.5-turbo"
            
            logger.warning(f"[AI FALLBACK] Triggering cross-provider fallback to {fallback.name}")
            self._record_metric(current_provider.name, "fallback") # Recorded as a fallback event initiated from original
            
            try:
                res = fallback.generate(fb_model, messages, is_json, **kwargs)
                logger.info(f"[AI SUCCESS] Fallback Provider {fallback.name} succeeded")
                self._record_metric(fallback.name, "success")
                self._set_cache(messages, res)
                return res
            except Exception as e:
                self._record_failure(fallback.name)
                logger.error(f"[AI FAILURE] Fallback Provider {fallback.name} also exhausted.")
                raise AIRetryException("All Provider Adapters exhausted.", retry_after=10)
        else:
            raise AIRetryException("Primary provider exhausted and no fallbacks available.", retry_after=10)


# ==========================================
# AI ENGINE SERVICE (Entrypoint)
# ==========================================
class AIEngineService:
    def __init__(self):
        self.router = AIRouter()

    def is_configured(self) -> bool:
        return any(p.is_configured() for p in self.router.providers.values())

    def _determine_complexity(self, message: str, context: dict) -> bool:
        combined = (context.get("system_prompt", "") + " " + message).lower()
        if "sales" in combined or "interested" in combined or "شراء" in combined or len(combined) > 4000:
            return True
        return False

    def generate_response(self, message: str, context: dict) -> str:
        if not self.is_configured():
            return "عذراً، نظام الذكاء الاصطناعي قيد الصيانة."
            
        messages = [{"role": "system", "content": context.get("system_prompt", "")}]
        if context.get("history"):
            messages.extend(context.get("history"))
            
        img = context.get("image_base64")
        if img:
            messages.append({"role": "user", "content": [{"type": "text", "text": message}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}]})
        else:
            messages.append({"role": "user", "content": message})

        is_complex = self._determine_complexity(message, context)
        is_downgraded = context.get("is_downgraded", False)

        return self.router.route_request(
            messages=messages, 
            is_json=False, 
            is_complex=is_complex, 
            is_downgraded=is_downgraded,
            temperature=0.7, 
            max_tokens=600
        )

    def generate_json_response(self, message: str, context: dict) -> str:
        if not self.is_configured():
            return '{"reply": "عذراً، نظام الذكاء الاصطناعي قيد الصيانة.", "intent": "none", "entities": {}}'

        messages = [{"role": "system", "content": context.get("system_prompt", "")}]
        if context.get("history"):
            messages.extend(context.get("history"))
            
        img = context.get("image_base64")
        if img:
            messages.append({"role": "user", "content": [{"type": "text", "text": message}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}]})
        else:
            messages.append({"role": "user", "content": message})

        is_complex = self._determine_complexity(message, context)
        is_downgraded = context.get("is_downgraded", False)

        return self.router.route_request(
            messages=messages, 
            is_json=True, 
            is_complex=is_complex, 
            is_downgraded=is_downgraded,
            temperature=0.3, 
            max_tokens=600
        )

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        # Fallback simplistic passthrough for OpenAI specific endpoint
        p = self.router.providers.get("openai")
        if p and p.is_configured():
            try:
                return p.client.audio.transcriptions.create(model="whisper-1", file=(filename, audio_bytes, "audio/ogg")).text
            except Exception as e:
                logger.error(f"Whisper Transcription Error: {e}")
        return ""

ai_engine = AIEngineService()
