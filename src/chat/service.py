import logging
import re
import requests
import base64
from src.core.database import SessionLocal
from src.stores.models import Store
from src.users.models import User
from src.chat.models import Conversation, Message
from src.orders.models import Order, OrderItem
from src.products.models import Product
from src.ai_engine.service import ai_engine

logger = logging.getLogger(__name__)

def send_telegram_msg(token, chat_id, text):
    print("DEBUG: Sending message to Telegram", chat_id, text)
    print("CHAT ID:", chat_id)
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": str(chat_id), "text": text})
    print("TELEGRAM RESPONSE:", response.status_code, response.text)

class ChatProcessingService:
    def handle_telegram_update(self, token: str, update: dict):
        if "message" not in update: return
        
        message = update["message"]
        text = message.get("text", "")
        user_id = str(message["from"]["id"])
        first_name = message["from"].get("first_name", "User")
        
        image_base64 = None
        if "photo" in message:
            try:
                photo = message["photo"][-1]
                file_id = photo["file_id"]
                file_info_res = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}").json()
                if file_info_res.get("ok"):
                    file_path = file_info_res["result"]["file_path"]
                    img_data = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}").content
                    image_base64 = base64.b64encode(img_data).decode("utf-8")
                text = message.get("caption", text)
            except Exception as e:
                logger.error(f"Failed to download image: {e}")
                
        voice_id = message.get("voice", {}).get("file_id") or message.get("audio", {}).get("file_id")
        if voice_id:
            try:
                file_info_res = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={voice_id}").json()
                if file_info_res.get("ok"):
                    file_path = file_info_res["result"]["file_path"]
                    audio_data = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}").content
                    transcribed_text = ai_engine.transcribe_audio(audio_data, filename="voice.ogg")
                    if text:
                        text = f"{text}\n[رسالة صوتية مفرغة]: {transcribed_text}".strip()
                    else:
                        text = transcribed_text
            except Exception as e:
                logger.error(f"Failed to process voice message: {e}")
                
        if not text and not image_base64: return
        
        db = SessionLocal()
        try:
            store = None
            for s in db.query(Store).filter(Store.status == 'active').all():
                if getattr(s, 'telegram_token', None) == token:
                    store = s
                    break
            if not store: return
            if not store.is_active: return # Ignore messages if store disabled
            
            from datetime import datetime
            if store.subscription_end_date and datetime.utcnow() > store.subscription_end_date:
                send_telegram_msg(token, user_id, "عذراً، المتجر مغلق مؤقتاً لانتهاء الاشتراك. يرجى مراجعة إدارة المتجر.")
                return
            
            user = db.query(User).filter(User.store_id == store.id, User.telegram_id == user_id).first()
            if not user:
                user = User(store_id=store.id, telegram_id=user_id, first_name=first_name, conversation_state="idle")
                db.add(user)
                db.commit()
                db.refresh(user)
                
            conversation = db.query(Conversation).filter(Conversation.user_id == user.id).first()
            if not conversation:
                conversation = Conversation(user_id=user.id)
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            if getattr(conversation, 'requires_human', False):
                # AI is muted because a human agent is handling the chat
                return

            # --- FINITE STATE MACHINE (Checkout Flow) ---
            if user.conversation_state == "checkout_address":
                if text.strip() in ["الغاء", "إلغاء", "cancel", "الغاء الطلب"]:
                    order = db.query(Order).filter(Order.id == user.active_order_id).first()
                    if order: order.status = "cancelled"
                    user.conversation_state = "idle"
                    user.active_order_id = None
                    db.commit()
                    send_telegram_msg(token, user_id, "تم إلغاء عملية الشراء. كيف يمكنني إفادتك؟")
                    return
                
                # Intelligent FSM Trap Protection
                question_words = ["بدي", "هل", "بكم", "شنو", "ليش", "كيف", "تخفيض", "راعيني", "غالي", "شو", "زبطني", "صورة"]
                is_question = any(word in text for word in question_words)
                if len(text) < 5 or is_question:
                    send_telegram_msg(token, user_id, "عذراً، أنت الآن في مرحلة إكمال الطلب 🛒 ولا يمكنني الرد على الاستفسارات هنا.\n\nالرجاء كتابة **عنوان الشحن** بالتفصيل،\nأو أرسل 'إلغاء' للعودة للمحادثة الطبيعية.")
                    return

                order = db.query(Order).filter(Order.id == user.active_order_id).first()
                if order:
                    order.shipping_address = text
                    user.conversation_state = "idle"
                    user.active_order_id = None
                    db.commit()
                    
                    history = db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.timestamp).all()
                    context = [{"role": h.role, "content": h.content} for h in history[-5:]]
                    confirm_prompt = ai_engine.generate_response(
                        system_prompt=f"العميل أرسل عنوان التوصيل الخاص به: '{text}'. مهمتك: أجب بلطافة وأخبره أنه تم تثبيت الطلب بنجاح وأنه سيشحن في أقرب وقت. لا تطلب معلومات إضافية واختتم المحادثة.",
                        user_message=text,
                        context=context,
                        
                    )
                    send_telegram_msg(token, user_id, confirm_prompt)
                return

            # --- Normal AI Flow ---
            msg_content = text if text else "[أرسل العميل صورة]"
            msg_user = Message(conversation_id=conversation.id, role="user", content=msg_content)
            db.add(msg_user)
            
            # Task 5 Tracking: follow_up_replied
            try:
                import json
                ctx = json.loads(conversation.context) if conversation.context else {}
                if ctx.get("auto_followed_up_at"):
                    logger.info(f"PERFORMANCE: follow_up_replied for Conv {conversation.id}")
                    ctx.pop("auto_followed_up_at", None)
                    ctx["has_replied_to_followup"] = True
                    conversation.context = json.dumps(ctx)
            except Exception as e: pass
            
            db.commit()
            
            history = db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.timestamp).all()
            context = [{"role": h.role, "content": h.content} for h in history[:-1][-10:]]
            
            products = db.query(Product).filter_by(store_id=store.id, is_active=True).all()
            inventory_context = "المخزون المتاح للبيع:\n"
            valid_ids = []
            for p in products:
                cat_str = f"[{p.category}]" if p.category else ""
                size_str = ""
                if getattr(p, 'has_sizes', False) and p.sizes:
                    import json
                    sz_dict = json.loads(p.sizes)
                    avail = [s for s, ok in sz_dict.items() if ok]
                    if avail: size_str = f" (مقاسات متوفرة: {', '.join(avail)})"
                img_str = f" [IMAGE: {p.image_url}]" if p.image_url else ""
                
                inventory_context += f"- ID({p.id}) {cat_str} {p.name}: {p.price} {store.currency}. {p.description}{size_str}{img_str}\n"
                valid_ids.append(str(p.id))
            
            full_system_prompt = f"أنت مندوب مبيعات لمتجر '{store.name}'. العميل اسمه '{user.first_name}'. العملة هي {store.currency}. لغة المتجر: {store.language}.\n"
            if store.has_branches and store.branch_names:
                full_system_prompt += f"**تنبيه:** المتجر يملك فروعاً في: {store.branch_names}. إذا سأل عن الموقع، اسأله أي فرع يفضل.\n"
            full_system_prompt += f"**نبرتك واسلوبك:** {store.ai_tone}.\n"
            full_system_prompt += f"**استراتيجيتك البيعية:** {store.sales_strategy}.\n\n"
            if store.policy:
                full_system_prompt += f"**سياسة المتجر وقاعدة المعرفة (التزم بها حرفياً):**\n{store.policy}\n\n"
            full_system_prompt += f"{inventory_context}\n\n"
            
            bank_str = ""
            if getattr(store, 'bank_account_number', None):
                bank_str = f"المتجر يدعم التحويل البنكي (الحساب: {store.bank_account_number} باسم {store.bank_account_name})."
                
            full_system_prompt += f"**معلومات الدفع والتوصيل:** {bank_str} أو الدفع عند الاستلام. يجب أن تخير العميل أيهما يفضل قبل أن تصدر أمر الشراء النهائي.\n\n"
            full_system_prompt += "تعليمات هامة جداً (CRITICAL RULES):\n"
            full_system_prompt += "1. LANGUAGE (اللغة): يجب عليك دائماً الرد على العميل بنفس اللغة التي يتحدث بها.\n"
            full_system_prompt += "2. الصور: إذا طلب صورة لمنتج، اكتب فقط رسالة عادية مع كود: [IMAGE: الرابط_المطابق_للمنتج_في_المخزون]\n"
            full_system_prompt += "3. الشكوى: في حال الشكوى المباشرة، أضف السطر السري نهاية الرد: [CATEGORY: COMPLAINT]\n"
            full_system_prompt += "4. الشراء: إذا اختار العميل المنتجات واختار مقاساً متاحاً (إن وجد) واختار طريقة الدفع وقدم إيصالاً للتحويل أو أكد رغبته بالدفع عند الاستلام، أضف السطر السري نهاية الرد: [CHECKOUT: رقم_المنتج]\n"
            full_system_prompt += "   هام جداً: مع كود CHECKOUT، اطلب منه إرسال 'عنوان التوصيل كاملاً' بلغته بالضبط لتأكيد إرسال الطلب.\n"
            full_system_prompt += "5. التحويل لبشري: لطلب الدعم البشري، أضف السطر السري نهاية الرد: [CATEGORY: HUMAN]\n"
            
            import json
            ctx_data = {}
            try:
                ctx_data = json.loads(conversation.context) if conversation.context else {}
            except Exception: pass
            
            last_status = ctx_data.get("lead_status", "")
            last_product = ctx_data.get("last_product", "")
            
            ai_mode_prompt = ""
            if getattr(store, "ai_mode", "sales") == "consultant":
                ai_mode_prompt = "أنت الآن في وضع مستشار (Consultant). قدم إجابات غنية بالمعلومات ونصائح مفصلة بدون إلحاح على البيع.\n"
            elif getattr(store, "ai_mode", "sales") == "support":
                ai_mode_prompt = "أنت الآن في وضع الدعم الفني (Support). قدم إجابات قصيرة ومباشرة لحل مشكلة العميل العاجلة.\n"
            else:
                cta_prompt = "اختتم كلامك دائماً بتوجيه العميل للخطوة التالية.\n"
                if last_status == "interested":
                    cta_prompt = "العميل مهتم جداً: اختتم رسالتك بطلب قوي ومباشر للشراء أو حجز المنتج (مثال: هل أؤكد طلبك الآن؟ هل تحب أن أجهز الرابط والدفع؟).\n"
                elif last_status == "needs_followup":
                    cta_prompt = "العميل يحتاج إلى مساعدة في اتخاذ القرار: اختتم رسالتك بسؤال توضيحي مرن (مثال: هل تبحث عن لون محدد؟ ما الحجم الذي تفضله؟).\n"
                elif last_status == "not_interested":
                    cta_prompt = "العميل غير مهتم حالياً: اختتم رسالتك باقتراح أو عرض لمنتج مختلف أو خصم قد يجذب انتباهه كبديل.\n"
                    
                memory_prompt = ""
                if last_product:
                    memory_prompt = f"تذكير: العميل أظهر سابقاً اهتماماً بـ '{last_product}'، يرجى الإشارة إليه بذكاء إذا كان مناسباً للسياق.\n"
                    
                ai_mode_prompt = f"أنت الآن في وضع المبيعات (Sales). كن مقنعاً جداً.\n{memory_prompt}{cta_prompt}"
                
            full_system_prompt += f"\n**سلوك الذكاء الاصطناعي:** {ai_mode_prompt}"
            full_system_prompt += """
تصنيف العميل (إلزامي): أضف في نهاية رسالتك، وفي سطر مستقل تماماً، هذا الكود فقط لتقييم العميل واستخراج بياناته:
{"lead_status":"interested"|"not_interested"|"needs_followup", "last_product":"المنتج هنا", "price_range":"السعر هنا", "intent":"نية العميل هنا"}
"""

            import time
            start_time = time.time()
            usage_info = {}
            reply = ai_engine.generate_response(message=text, context={'system_prompt': full_system_prompt, 'history': context,
                'image_base64': image_base64, 'store_id': getattr(store, 'id', None), 'is_downgraded': False}, out_usage=usage_info)
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            try:
                from src.chat.models import AILog
                ai_log = AILog(
                    store_id=store.id,
                    conversation_id=conversation.id,
                    prompt_tokens=usage_info.get('prompt_tokens') or (len(full_system_prompt) // 4 if full_system_prompt else 0),
                    completion_tokens=usage_info.get('completion_tokens') or (len(reply) // 4 if reply else 0),
                    processing_time_ms=processing_time_ms
                )
                db.add(ai_log)
                ai_engine.invalidate_monthly_tokens(store.id)
            except Exception as e:
                logger.error(f"Failed to write AILog: {e}")
            
            msg_ai = Message(conversation_id=conversation.id, role="assistant", content=reply)
            db.add(msg_ai)
            db.commit()
            
            clean_reply = reply.strip()
            import json
            import re
            
            status = None
            json_match = re.search(r'(\{[\s\S]*?"lead_status"[\s\S]*?\})\s*$', clean_reply)
            
            try:
                ctx = json.loads(conversation.context) if conversation.context else {}
            except Exception:
                ctx = {}
                
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                    status = extracted_data.get("lead_status")
                    clean_reply = clean_reply[:json_match.start()].strip()
                    
                    ctx["last_product"] = extracted_data.get("last_product", ctx.get("last_product"))
                    ctx["price_range"] = extracted_data.get("price_range", ctx.get("price_range"))
                    ctx["intent"] = extracted_data.get("intent", ctx.get("intent"))
                except BaseException as e:
                    logger.error(f"Failed parsing extended JSON: {e}")
                    status = None
                    
            if not status or status not in ["interested", "not_interested", "needs_followup"]:
                msg_count = db.query(Message).filter_by(conversation_id=conversation.id).count()
                status = "needs_followup" if msg_count >= 2 else "not_interested"

            ctx["lead_status"] = status
            
            conversation.context = json.dumps(ctx)
            db.commit()
            logger.info(f"[LEAD INTELLIGENCE TG] Conv {conversation.id} classified: {status}")

            # Handle categories parsing
            if '[CATEGORY: COMPLAINT]' in clean_reply:
                clean_reply = clean_reply.replace('[CATEGORY: COMPLAINT]', '').strip()
                conversation.category = 'complaint'
                db.commit()
                # Notify admin via console log simulation
                if store.owner_email: print(f"ALERT: Complaint email sent to {store.owner_email}!")
            
            if '[CATEGORY: HUMAN]' in clean_reply:
                clean_reply = clean_reply.replace('[CATEGORY: HUMAN]', '').strip()
                conversation.requires_human = True
                conversation.category = 'inquiry'
                db.commit()
                if store.owner_phone:
                    from urllib.parse import quote
                    wa_msg = quote(f"مرحباً، أنا العميل {user.first_name} وأحتاج لمساعدة بخصوص المتجر.")
                    wa_link = f"https://wa.me/{store.owner_phone.replace('+', '')}?text={wa_msg}"
                    clean_reply += f"\n\n👨‍💼 يمكنك التحدث مع الدعم الفني مباشرة وبشكل أسرع عبر واتساب من خلال الضغط على الرابط التالي:\n{wa_link}"

            # 1. Parse Checkout
            checkout_match = re.search(r'\[CHECKOUT:\s*(\d+)\]', clean_reply)
            if checkout_match:
                product_id = int(checkout_match.group(1).strip())
                clean_reply = re.sub(r'\[CHECKOUT:\s*\d+\]', '', clean_reply).strip()
                
                # FORCE category to order if checkout initiated, overriding false positive complaints
                conversation.category = 'order'
                db.commit()
                    
                p = db.query(Product).filter_by(id=product_id, store_id=store.id).first()
                if p:
                    order = Order(user_id=user.id, store_id=store.id, total_amount=p.price, status="paid")
                    db.add(order)
                    
                    if not ctx.get("converted"):
                        ctx["converted"] = True
                        if ctx.get("follow_up_sent"):
                            ctx["conversion_after_followup"] = True
                            logger.info(f"PERFORMANCE: conversion_after_followup triggered for Conv {conversation.id}")
                        conversation.context = json.dumps(ctx)
                        
                    db.commit()
                    db.refresh(order)
                    
                    order_item = OrderItem(order_id=order.id, product_id=p.id, quantity=1, price_at_purchase=p.price)
                    db.add(order_item)
                    
                    user.conversation_state = "checkout_address"
                    user.active_order_id = order.id
                    db.commit()
                    
                    send_telegram_msg(token, user_id, clean_reply)
                    return
            
            # 2. Parse Image
            img_match = re.search(r'\[IMAGE:\s*(https?://[^\]]+)\]', clean_reply)
            if img_match:
                photo_url = img_match.group(1).strip()
                clean_reply = re.sub(r'\[IMAGE:\s*https?://[^\]]+\]', '', clean_reply).strip()
                res = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", json={"chat_id": user_id, "photo": photo_url, "caption": clean_reply})
                if not res.json().get("ok"): send_telegram_msg(token, user_id, clean_reply)
            else:
                send_telegram_msg(token, user_id, clean_reply)
            
        except Exception as e:
            logger.error(f"Error handling telegram update: {e}")
        finally:
            db.close()

    def handle_whatsapp_update(self, token: str, update: dict):
        try:
            entry = update.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            if not messages: return
            
            message = messages[0]
            text = message.get("text", {}).get("body", "")
            user_phone = message.get("from")
            first_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "WhatsApp User") if value.get("contacts") else "WhatsApp User"
            
            if not text: return
            
            db = SessionLocal()
            store = None
            for s in db.query(Store).filter(Store.status == 'active').all():
                if getattr(s, 'whatsapp_token', None) == token:
                    store = s
                    break
            if not store or not store.is_active: return
            from datetime import datetime
            if store.subscription_end_date and datetime.utcnow() > store.subscription_end_date: return
            
            # Using telegram_id field generically as external platform user ID
            user = db.query(User).filter(User.store_id == store.id, User.telegram_id == user_phone).first()
            if not user:
                user = User(store_id=store.id, telegram_id=user_phone, first_name=first_name, conversation_state="idle")
                db.add(user)
                db.commit()
                db.refresh(user)
                
            conversation = db.query(Conversation).filter(Conversation.user_id == user.id).first()
            if not conversation:
                conversation = Conversation(user_id=user.id)
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            msg_user = Message(conversation_id=conversation.id, role="user", content=text)
            db.add(msg_user)
            
            # Task 5 Tracking: follow_up_replied
            try:
                import json
                ctx = json.loads(conversation.context) if conversation.context else {}
                if ctx.get("follow_up_sent") and not ctx.get("follow_up_replied"):
                    logger.info(f"PERFORMANCE: follow_up_replied for Conv {conversation.id}")
                    ctx["follow_up_replied"] = True
                    conversation.context = json.dumps(ctx)
            except Exception as e: pass
            
            db.commit()
            
            history = db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.id.asc()).all()
            context = [{"role": h.role, "content": h.content} for h in history[:-1][-10:]]
            
            full_system_prompt = f"أنت مندوب مبيعات لمتجر '{store.name}' يتواصل عبر WhatsApp. العميل مسجل بالاسم '{user.first_name}'.\n"
            if store.policy: full_system_prompt += f"سياسة المتجر الواجب الالتزام بها: {store.policy}\n"
            
            import json
            ctx_data = {}
            try:
                ctx_data = json.loads(conversation.context) if conversation.context else {}
            except Exception: pass
            
            last_status = ctx_data.get("lead_status", "")
            last_product = ctx_data.get("last_product", "")
            
            ai_mode_prompt = ""
            if getattr(store, "ai_mode", "sales") == "consultant":
                ai_mode_prompt = "أنت الآن في وضع مستشار (Consultant). قدم إجابات غنية بالمعلومات ونصائح مفصلة بدون إلحاح على البيع.\n"
            elif getattr(store, "ai_mode", "sales") == "support":
                ai_mode_prompt = "أنت الآن في وضع الدعم الفني (Support). قدم إجابات قصيرة ومباشرة لحل مشكلة العميل العاجلة.\n"
            else:
                cta_prompt = "اختتم كلامك دائماً بتوجيه العميل للخطوة التالية.\n"
                if last_status == "interested":
                    cta_prompt = "العميل مهتم جداً: اختتم رسالتك بطلب قوي ومباشر للشراء أو حجز المنتج (مثال: هل أؤكد طلبك الآن؟ هل تحب أن أجهز الرابط والدفع؟).\n"
                elif last_status == "needs_followup":
                    cta_prompt = "العميل يحتاج إلى مساعدة في اتخاذ القرار: اختتم رسالتك بسؤال توضيحي مرن (مثال: هل تبحث عن لون محدد؟ ما الحجم الذي تفضله؟).\n"
                elif last_status == "not_interested":
                    cta_prompt = "العميل غير مهتم حالياً: اختتم رسالتك باقتراح أو عرض لمنتج مختلف أو خصم قد يجذب انتباهه كبديل.\n"
                    
                memory_prompt = ""
                if last_product:
                    memory_prompt = f"تذكير: العميل أظهر سابقاً اهتماماً بـ '{last_product}'، يرجى الإشارة إليه بذكاء إذا كان مناسباً للسياق.\n"
                    
                ai_mode_prompt = f"أنت الآن في وضع المبيعات (Sales). كن مقنعاً جداً.\n{memory_prompt}{cta_prompt}"
                
            full_system_prompt += f"\n**سلوك الذكاء الاصطناعي:** {ai_mode_prompt}"
            full_system_prompt += """
تصنيف العميل (إلزامي): أضف في نهاية رسالتك، وفي سطر مستقل تماماً، هذا الكود فقط لتقييم العميل واستخراج بياناته:
{"lead_status":"interested"|"not_interested"|"needs_followup", "last_product":"المنتج هنا", "price_range":"السعر هنا", "intent":"نية العميل هنا"}
"""
            reply = ai_engine.generate_response(message=text, context={'system_prompt': full_system_prompt, 'history': context, 'store_id': getattr(store, 'id', None), 'is_downgraded': False})
            
            clean_reply = reply.strip()
            import json
            import re
            
            status = None
            json_match = re.search(r'(\{[\s\S]*?"lead_status"[\s\S]*?\})\s*$', clean_reply)
            
            try:
                ctx = json.loads(conversation.context) if conversation.context else {}
            except Exception:
                ctx = {}
                
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                    status = extracted_data.get("lead_status")
                    clean_reply = clean_reply[:json_match.start()].strip()
                    
                    ctx["last_product"] = extracted_data.get("last_product", ctx.get("last_product"))
                    ctx["price_range"] = extracted_data.get("price_range", ctx.get("price_range"))
                    ctx["intent"] = extracted_data.get("intent", ctx.get("intent"))
                except BaseException as e:
                    logger.error(f"Failed parsing extended JSON WA: {e}")
                    status = None
                    
            if not status or status not in ["interested", "not_interested", "needs_followup"]:
                msg_count = db.query(Message).filter_by(conversation_id=conversation.id).count()
                status = "needs_followup" if msg_count >= 2 else "not_interested"

            ctx["lead_status"] = status
            
            conversation.context = json.dumps(ctx)
            db.commit()
            logger.info(f"[LEAD INTELLIGENCE WA] Conv {conversation.id} classified: {status}")
            
            checkout_match = re.search(r'\[CHECKOUT:\s*(\d+)\]', clean_reply)
            if checkout_match:
                product_id = int(checkout_match.group(1).strip())
                clean_reply = re.sub(r'\[CHECKOUT:\s*\d+\]', '', clean_reply).strip()
                conversation.category = 'order'
                db.commit()
                p = db.query(Product).filter_by(id=product_id, store_id=store.id).first()
                if p:
                    order = Order(user_id=user.id, store_id=store.id, total_amount=p.price, status="paid")
                    db.add(order)
                    
                    if not ctx.get("converted"):
                        ctx["converted"] = True
                        if ctx.get("follow_up_sent"):
                            ctx["conversion_after_followup"] = True
                            logger.info(f"PERFORMANCE: conversion_after_followup triggered for Conv {conversation.id}")
                        conversation.context = json.dumps(ctx)
                        
                    db.commit()
                    db.refresh(order)
                    order_item = OrderItem(order_id=order.id, product_id=p.id, quantity=1, price_at_purchase=p.price)
                    db.add(order_item)
                    user.conversation_state = "checkout_address"
                    user.active_order_id = order.id
                    db.commit()
                    
            reply = clean_reply
            
            msg_ai = Message(conversation_id=conversation.id, role="assistant", content=reply)
            db.add(msg_ai)
            db.commit()
            
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            if phone_number_id:
                url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
                headers = {"Authorization": f"Bearer {store.whatsapp_token}", "Content-Type": "application/json"}
                payload = {
                    "messaging_product": "whatsapp",
                    "to": user_phone,
                    "type": "text",
                    "text": {"body": reply}
                }
                res = requests.post(url, headers=headers, json=payload)
                if not res.ok:
                    logger.error(f"WhatsApp send failed: {res.text}")
            else:
                logger.error("Could not find phone_number_id in WhatsApp webhook payload.")

        except Exception as e:
            logger.error(f"Error handling WhatsApp update: {e}")
        finally:
            if 'db' in locals(): db.close()

    def handle_instagram_update(self, token: str, update: dict):
        try:
            object_type = update.get("object")
            if object_type != "instagram": return
            
            entry = update.get("entry", [{}])[0]
            messaging_events = entry.get("messaging", [])
            if not messaging_events: return
            
            message_event = messaging_events[0]
            sender_id = message_event.get("sender", {}).get("id")
            recipient_id = message_event.get("recipient", {}).get("id")
            message = message_event.get("message", {})
            text = message.get("text", "")
            
            first_name = "Instagram User" 
            
            if not text or message.get("is_echo") == True:
                return
                
            db = SessionLocal()
            store = None
            for s in db.query(Store).filter(Store.status == 'active').all():
                if getattr(s, 'instagram_token', None) == token:
                    store = s
                    break
            if not store or not store.is_active: return
            from datetime import datetime
            if store.subscription_end_date and datetime.utcnow() > store.subscription_end_date: return
            
            user = db.query(User).filter(User.store_id == store.id, User.telegram_id == str(sender_id)).first()
            if not user:
                user = User(store_id=store.id, telegram_id=str(sender_id), first_name=first_name, conversation_state="idle")
                db.add(user)
                db.commit()
                db.refresh(user)
                
            conversation = db.query(Conversation).filter(Conversation.user_id == user.id).first()
            if not conversation:
                conversation = Conversation(user_id=user.id)
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            if getattr(conversation, 'requires_human', False):
                return

            msg_user = Message(conversation_id=conversation.id, role="user", content=text)
            db.add(msg_user)
            
            # Task 5 Tracking: follow_up_replied
            try:
                import json
                ctx = json.loads(conversation.context) if conversation.context else {}
                if ctx.get("follow_up_sent") and not ctx.get("follow_up_replied"):
                    logger.info(f"PERFORMANCE: follow_up_replied for Conv {conversation.id}")
                    ctx["follow_up_replied"] = True
                    conversation.context = json.dumps(ctx)
            except Exception as e: pass
            
            db.commit()
            
            history = db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.id.asc()).all()
            context = [{"role": h.role, "content": h.content} for h in history[:-1][-10:]]
            
            full_system_prompt = f"أنت مندوب مبيعات لمتجر '{store.name}' يتواصل عبر Instagram. العميل مسجل بالاسم '{user.first_name}'.\n"
            if store.policy: full_system_prompt += f"سياسة المتجر الواجب الالتزام بها: {store.policy}\n"
            
            import json
            ctx_data = {}
            try:
                ctx_data = json.loads(conversation.context) if conversation.context else {}
            except Exception: pass
            
            last_status = ctx_data.get("lead_status", "")
            last_product = ctx_data.get("last_product", "")
            
            ai_mode_prompt = ""
            if getattr(store, "ai_mode", "sales") == "consultant":
                ai_mode_prompt = "أنت الآن في وضع مستشار (Consultant). قدم إجابات غنية بالمعلومات ونصائح مفصلة بدون إلحاح على البيع.\n"
            elif getattr(store, "ai_mode", "sales") == "support":
                ai_mode_prompt = "أنت الآن في وضع الدعم الفني (Support). قدم إجابات قصيرة ومباشرة لحل مشكلة العميل العاجلة.\n"
            else:
                cta_prompt = "اختتم كلامك دائماً بتوجيه العميل للخطوة التالية.\n"
                if last_status == "interested":
                    cta_prompt = "العميل مهتم جداً: اختتم رسالتك بطلب قوي ومباشر للشراء أو حجز المنتج (مثال: هل أؤكد طلبك الآن؟ هل تحب أن أجهز الرابط والدفع؟).\n"
                elif last_status == "needs_followup":
                    cta_prompt = "العميل يحتاج إلى مساعدة في اتخاذ القرار: اختتم رسالتك بسؤال توضيحي مرن (مثال: هل تبحث عن لون محدد؟ ما الحجم الذي تفضله؟).\n"
                elif last_status == "not_interested":
                    cta_prompt = "العميل غير مهتم حالياً: اختتم رسالتك باقتراح أو عرض لمنتج مختلف أو خصم قد يجذب انتباهه كبديل.\n"
                    
                memory_prompt = ""
                if last_product:
                    memory_prompt = f"تذكير: العميل أظهر سابقاً اهتماماً بـ '{last_product}'، يرجى الإشارة إليه بذكاء إذا كان مناسباً للسياق.\n"
                    
                ai_mode_prompt = f"أنت الآن في وضع المبيعات (Sales). كن مقنعاً جداً.\n{memory_prompt}{cta_prompt}"
                
            full_system_prompt += f"\n**سلوك الذكاء الاصطناعي:** {ai_mode_prompt}"
            full_system_prompt += """
تصنيف العميل (إلزامي): أضف في نهاية رسالتك، وفي سطر مستقل تماماً، هذا الكود فقط لتقييم العميل واستخراج بياناته:
{"lead_status":"interested"|"not_interested"|"needs_followup", "last_product":"المنتج هنا", "price_range":"السعر هنا", "intent":"نية العميل هنا"}
"""
            reply = ai_engine.generate_response(message=text, context={'system_prompt': full_system_prompt, 'history': context, 'store_id': getattr(store, 'id', None), 'is_downgraded': False})
            
            clean_reply = reply.strip()
            clean_reply = reply.strip()
            import json
            import re
            
            status = None
            json_match = re.search(r'(\{[\s\S]*?"lead_status"[\s\S]*?\})\s*$', clean_reply)
            
            try:
                ctx = json.loads(conversation.context) if conversation.context else {}
            except Exception:
                ctx = {}
                
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                    status = extracted_data.get("lead_status")
                    clean_reply = clean_reply[:json_match.start()].strip()
                    
                    ctx["last_product"] = extracted_data.get("last_product", ctx.get("last_product"))
                    ctx["price_range"] = extracted_data.get("price_range", ctx.get("price_range"))
                    ctx["intent"] = extracted_data.get("intent", ctx.get("intent"))
                except BaseException as e:
                    logger.error(f"Failed parsing extended JSON IG: {e}")
                    status = None
                    
            if not status or status not in ["interested", "not_interested", "needs_followup"]:
                msg_count = db.query(Message).filter_by(conversation_id=conversation.id).count()
                status = "needs_followup" if msg_count >= 2 else "not_interested"

            ctx["lead_status"] = status
            
            conversation.context = json.dumps(ctx)
            db.commit()
            logger.info(f"[LEAD INTELLIGENCE IG] Conv {conversation.id} classified: {status}")
            
            checkout_match = re.search(r'\[CHECKOUT:\s*(\d+)\]', clean_reply)
            if checkout_match:
                product_id = int(checkout_match.group(1).strip())
                clean_reply = re.sub(r'\[CHECKOUT:\s*\d+\]', '', clean_reply).strip()
                conversation.category = 'order'
                db.commit()
                p = db.query(Product).filter_by(id=product_id, store_id=store.id).first()
                if p:
                    order = Order(user_id=user.id, store_id=store.id, total_amount=p.price, status="paid")
                    db.add(order)
                    
                    if not ctx.get("converted"):
                        ctx["converted"] = True
                        if ctx.get("follow_up_sent"):
                            ctx["conversion_after_followup"] = True
                            logger.info(f"PERFORMANCE: conversion_after_followup triggered for Conv {conversation.id}")
                        conversation.context = json.dumps(ctx)
                        
                    db.commit()
                    db.refresh(order)
                    order_item = OrderItem(order_id=order.id, product_id=p.id, quantity=1, price_at_purchase=p.price)
                    db.add(order_item)
                    user.conversation_state = "checkout_address"
                    user.active_order_id = order.id
                    db.commit()
                    
            reply = clean_reply
            
            msg_ai = Message(conversation_id=conversation.id, role="assistant", content=reply)
            db.add(msg_ai)
            db.commit()
            
            url = "https://graph.facebook.com/v17.0/me/messages"
            headers = {"Authorization": f"Bearer {store.instagram_token}", "Content-Type": "application/json"}
            payload = {
                "recipient": {"id": sender_id},
                "message": {"text": reply}
            }
            res = requests.post(url, headers=headers, json=payload)
            if not res.ok:
                logger.error(f"Instagram send failed: {res.text}")

        except Exception as e:
            logger.error(f"Error handling Instagram update: {e}")
        finally:
            if 'db' in locals(): db.close()

