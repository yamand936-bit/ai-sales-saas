from werkzeug.security import check_password_hash
from src.api.middlewares import merchant_required
from pydantic import ValidationError
from src.products.schemas import ProductCreate
from src.merchant.schemas import AIConfigUpdate

from flask import Blueprint, request, jsonify, render_template, redirect, session, flash, current_app, Response
from sqlalchemy import func
import json
import datetime



from src.utils.i18n import get_t
from src.core.config import settings
from src.merchant.service import MerchantService

merchant_bp = Blueprint('merchant', __name__)



@merchant_bp.route("/merchant/<int:store_id>/add_product", methods=["POST"])
@merchant_required
def add_product(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    name = request.form.get("name")
    price = float(request.form.get("price", 0))
    desc = request.form.get("description")
    image_url = request.form.get("image_url")
    category = request.form.get("category")
    is_service = request.form.get("is_service") == "on"
    booking_link = request.form.get("booking_link", "")
    type_val = request.form.get("type", "product")
    duration = request.form.get("duration")
    duration = int(duration) if duration else None

    data = {
        "name": name, 
        "price": price, 
        "description": desc, 
        "image_url": image_url, 
        "category": category, 
        "sizes": "{}",
        "is_service": is_service,
        "booking_link": booking_link,
        "type": type_val,
        "duration": duration
    }
    MerchantService.create_product(store_id, data)
    flash("Product added", "success")
    return redirect("/dashboard")

@merchant_bp.route("/merchant/<int:store_id>/toggle_product/<int:product_id>", methods=["POST"])
@merchant_required
def toggle_product(store_id, product_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    products = MerchantService.get_products(store_id)
    product = next((p for p in products if p.id == product_id), None)
    if product:
        MerchantService.update_product(product_id, {"is_active": not product.is_active})
        flash("Product status updated", "success")
    return redirect("/dashboard")

@merchant_bp.route("/merchant/<int:store_id>/delete_product/<int:product_id>", methods=["POST"])
@merchant_required
def delete_product(store_id, product_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    MerchantService.delete_product(product_id)
    flash("Product deleted", "success")
    return redirect("/dashboard")

@merchant_bp.route("/merchant/<int:store_id>/settings", methods=["POST"])
@merchant_required
def update_settings(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    store = MerchantService.get_store(store_id)
    if store:
        try:
            data = request.form.to_dict()
            if not data.get("ai_mode"): data["ai_mode"] = getattr(store, "ai_mode", "off")
            if not data.get("ai_tone"): data["ai_tone"] = getattr(store, "ai_tone", "friendly")
            if not data.get("policy"): data["policy"] = getattr(store, "policy", "")
            
            validated = AIConfigUpdate(**data)
            MerchantService.update_ai_config(store_id, validated.model_dump())
            flash("Settings saved!", "success")
        except ValidationError as e:
            flash(f"Validation Error: {e.errors()[0]['msg']}", "error")
    return redirect("/dashboard")

@merchant_bp.route("/merchant/<int:store_id>/broadcast", methods=["POST"])
@merchant_required
def merchant_broadcast_endpoint(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    msg = request.json.get("message") if request.is_json else request.form.get("message")
    from src.chat.tasks import send_telegram_message
    
    store = MerchantService.get_store(store_id)
    if store and store.telegram_token and msg:
        users = MerchantService.get_users(store_id)
        for u in users:
            if getattr(u, "telegram_id", None):
                send_telegram_message.delay(store.telegram_token, u.telegram_id, msg)
    return jsonify({"status": "success"}), 200

@merchant_bp.route("/merchant/<int:store_id>/order/<int:order_id>/approve", methods=["POST"])
@merchant_required
def approve_order(store_id, order_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    order = MerchantService.update_order_status(order_id, "paid")
    if not order:
        return "Order not found", 404
    flash("Order approved!", "success")
    return redirect("/dashboard")

@merchant_bp.route("/api/merchant/<int:store_id>/messages/<int:user_id>", methods=["GET"])
@merchant_required
def get_messages(store_id, user_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    user = MerchantService.get_user(user_id, store_id)
    if not user: return jsonify({"messages": []})
    all_c = MerchantService.get_conversations(session.get('store_id'))
    conv = next((c for c in all_c if c.user_id == user_id), None)
    if not conv:
        return jsonify({"messages": []})
    msgs = MerchantService.get_messages(conv.id)
    return jsonify({"messages": [{"role": m.role, "content": m.content, "time": m.timestamp.strftime('%H:%M')} for m in msgs[-50:]]})

@merchant_bp.route("/merchant/conversations", methods=["GET"])
@merchant_required
def merchant_conversations_endpoint():
    print("API HIT: /merchant/conversations")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    
    users = MerchantService.get_users(store_id)
    user_ids = [u.id for u in users]
    convs = MerchantService.get_conversations(store_id)
    
    data = []
    for conv in convs:
        msgs = MerchantService.get_messages(conv.id)
        last_msg = msgs[-1] if msgs else None
        user = next((u for u in users if u.id == conv.user_id), None)
        data.append({
            "id": user.id if user else "Unknown",
            "name": user.first_name if user else "Unknown",
            "last_message": last_msg.content if last_msg else None,
            "last_message_time": last_msg.timestamp.strftime('%H:%M') if last_msg else None
        })
    return jsonify({"conversations": data})

@merchant_bp.route("/merchant/users", methods=["GET"])
@merchant_required
def merchant_users_endpoint():
    print("API HIT: /merchant/users")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    
    users = MerchantService.get_users(store_id)
    data = [{"id": u.id, "name": u.first_name, "telegram_id": u.telegram_id} for u in users]
    return jsonify({"users": data})

@merchant_bp.route("/merchant/<int:store_id>/toggle_ai/<int:user_id>", methods=["POST"])
@merchant_required
def toggle_ai(store_id, user_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    user = MerchantService.get_user(user_id, store_id)
    if not user: return redirect("/dashboard")
    all_c = MerchantService.get_conversations(session.get('store_id'))
    conv = next((c for c in all_c if c.user_id == user_id), None)
    if conv:
        MerchantService.toggle_conversation_human_mode(conv.id)
    return redirect("/dashboard")

@merchant_bp.route("/merchant/<int:store_id>/toggle_system_ai", methods=["POST"])
@merchant_required
def toggle_system_ai(store_id):
    if store_id != session.get("store_id"): return jsonify({"error": "Forbidden"}), 403
    store = MerchantService.get_store(store_id)
    if store:
        ai_enabled = not getattr(store, "ai_enabled", False)
        MerchantService.update_ai_config(store_id, {"ai_enabled": ai_enabled})
        return jsonify({"status": "success", "ai_enabled": ai_enabled})
    return jsonify({"error": "Store not found"}), 404

@merchant_bp.route("/merchant/<int:store_id>/reply/<telegram_id>", methods=["POST"])
@merchant_required
def merchant_reply(store_id, telegram_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    from src.chat.service import send_telegram_msg
    store = MerchantService.get_store(store_id)
    user = MerchantService.get_user_by_telegram(telegram_id, store_id)
    if not store or not user:
        return jsonify({"error": "Not found"}), 404
        
    action_val = request.form.get("action_val")
    reply_msg = request.form.get("reply_msg")
    
    all_c = MerchantService.get_conversations(store.id)
    conv = next((c for c in all_c if c.user_id == user.id), None)
    
    if reply_msg:
        send_telegram_msg(store.telegram_token, telegram_id, reply_msg)
        if conv:
            new_msg = MerchantService.add_message(conversation_id=conv.id, role="assistant", content=reply_msg)
            
    if action_val == 'resolve' and conv:
        MerchantService.resolve_conversation(conv.id)
        
    return jsonify({"success": True})

@merchant_bp.route("/merchant/<int:store_id>/stream")
@merchant_required
def merchant_stream(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    def generate():
        import time
        while True:
            yield "data: {\"type\": \"heartbeat\"}\n\n"
            time.sleep(15)
    return Response(generate(), mimetype="text/event-stream")

@merchant_bp.route("/api/preview_ai", methods=["POST"])
@merchant_required
def preview_ai():
    import openai
    prompt = request.form.get("prompt")
    try:
        store = MerchantService.get_store(session["store_id"])
        openai.api_key = settings.OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=store.ai_model or "gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": store.policy or "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
        return reply
    except Exception as e:
        return str(e), 500

@merchant_bp.route("/merchant/<int:store_id>/auto_followup", methods=["POST"])
@merchant_required
def auto_followup(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    try:
        from src.chat.service import send_telegram_msg
        from src.ai_engine.service import ai_engine
        import json
        
        store = MerchantService.get_store(store_id)
        if not store or not store.ai_enabled:
            return jsonify({"status": "error", "message": "Store AI inactive"}), 400
            
        conversations = MerchantService.get_conversations(store.id)
        follow_ups_sent = 0
        
        try:
            feats = json.loads(store.features) if store.features else {}
            delay_mins = int(feats.get("followup_delay", 60))
        except Exception:
            delay_mins = 60
            
        delay_mins = max(30, delay_mins) # Task 2: minimum 30 minutes cooldown
        cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=delay_mins)

        import logging
        logger = logging.getLogger(__name__)

        for conv in conversations:
            ctx = {}
            if conv.context:
                try:
                    ctx = json.loads(conv.context)
                except Exception: pass
            
            if ctx.get("auto_followed_up_at"):
                logger.info(f"AFU Skip Conv {conv.id}: Already followed up.")
                continue
                
            msgs = MerchantService.get_messages(conv.id)
            
            # Task 2: conversation has at least 2 messages
            if len(msgs) < 2:
                logger.info(f"AFU Skip Conv {conv.id}: Less than 2 messages.")
                continue
            
            last_msg = msgs[-1]
            last_ai_msg = next((m for m in reversed(msgs) if m.role == 'assistant'), None)
            
            # Task 2: last message from user
            if last_msg.role != 'user':
                logger.info(f"AFU Skip Conv {conv.id}: Last message not from user.")
                continue
                
            if last_msg.timestamp >= cutoff_time:
                continue

            # Task 2: last AI message was NOT already a question
            if last_ai_msg:
                ai_text = last_ai_msg.content.strip()
                if ai_text.endswith("؟") or ai_text.endswith("?") or "هل تحتاج مساعدة" in ai_text or "Can I help" in ai_text:
                    logger.info(f"AFU Skip Conv {conv.id}: Last AI message was already a question.")
                    continue

            # Task 3: Follow-Up Filtering (Short user message)
            user_text_lower = last_msg.content.strip().lower()
            short_dismissals = ["ok", "thanks", "شكرا", "تمام", "يعطيك العافية", "طيب", "حسنا", "لا شكرا", "no thanks"]
            if len(user_text_lower) < 3 or any(user_text_lower == word for word in short_dismissals):
                logger.info(f"AFU Skip Conv {conv.id}: Last message was short/dismissal ('{user_text_lower}')")
                continue
                
            # Task 3: Follow-Up Filtering (Order completed)
            if last_ai_msg and getattr(conv, 'category', '') == 'checkout':
                logger.info(f"AFU Skip Conv {conv.id}: Conversation is in checkout/completed state.")
                continue
            checkout_indicators = ["[CHECKOUT:", "تم تثبيت الطلب بنجاح"]
            if any(ind in h.content for h in msgs[-5:]):
                logger.info(f"AFU Skip Conv {conv.id}: Conversation indicates order completion/checkout recently.")
                continue

            # Task 3: Improve follow-up message contextual quality
            context = [{"role": h.role, "content": h.content} for h in msgs[-5:]]
            sys_prompt = f"أنت مندوب مبيعات المتجر '{store.name}'. العميل تواصل معك مؤخراً وبدا مهتماً ثم توقف عن الرد. رسالتك السابقة له كانت: '{last_ai_msg.content if last_ai_msg else ''}'. \nالمطلوب: أرسل رسالة متابعة طبيعية، ودودة، وقصيرة جداً، تستند إلى آخر موضوع تحدثتم فيه بشكل ذكي. تجنب تكرار الكلام السابق، وتجنب الأسئلة النمطية العائمة مثل 'هل تحتاج مساعدة؟'. لا تستخدم أي مقدمات."
            
            ai_ctx = {'system_prompt': sys_prompt, 'history': context, 'store_id': getattr(store, 'id', None), 'is_downgraded': False}
            reply = ai_engine.generate_response(message="[SYSTEM TRIGGER]: العميل غير نشط، يرجى إرسال رسالة متابعة ذكية.", context=ai_ctx)

            # Task 5: Log follow_up_sent explicitly
            logger.info(f"PERFORMANCE: follow_up_sent for Conv {conv.id}")
            logger.info(f"AFU Triggered Conv {conv.id}: Sent follow-up -> {reply}")

            msg_ai = MerchantService.add_message(conversation_id=conv.id, role="assistant", content=reply)
            
            
            ctx["auto_followed_up_at"] = datetime.datetime.utcnow().isoformat()
            ctx["follow_up_sent"] = True
            MerchantService.update_conversation_context(conv.id, json.dumps(ctx))
            
            if conv.channel == "telegram" and getattr(store, "telegram_token", None) and getattr(conv.user, "telegram_id", None):
                send_telegram_msg(store.telegram_token, conv.user.telegram_id, reply)
                
            follow_ups_sent += 1

        return jsonify({"status": "success", "follow_ups_sent": follow_ups_sent})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



# ================================
# GLOBAL ROUTES
# ================================

@merchant_bp.route("/")
def index():
    return redirect("/login")

@merchant_bp.route("/set_lang/<lang>", endpoint="set_language")
def set_language(lang):
    if lang in ["ar", "en", "tr"]:
        session["lang"] = lang
    return redirect(request.referrer or "/")

@merchant_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/login")

# ================================
# MERCHANT ROUTES
# ================================
@merchant_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        store_id = request.form.get("store_id", "").strip()
        email = request.form.get("email") # Fallback
        password = request.form.get("password")
        
        store = None
        if store_id.isdigit():
            store = MerchantService.get_store(int(store_id))
        elif store_id:
            store = MerchantService.get_store_by_email(store_id)
        elif email:
             store = MerchantService.get_store_by_email(email)
             
        if store and check_password_hash(store.password_hash, password):
            session.permanent = True
            session["role"] = "merchant"
            session["store_id"] = store.id
            session["lang"] = "ar"
            return redirect("/dashboard")
        flash("Invalid email or password", "error")
    return render_template("login.html")

@merchant_bp.route("/dashboard")
@merchant_required
def dashboard():
    store_id = session.get("store_id")
    data = MerchantService.get_dashboard(store_id)
    if not data:
        session.clear()
        return redirect("/login")
    return render_template("merchant.html", **data)

@merchant_bp.route("/inventory", methods=["GET", "POST"])
@merchant_required
def inventory():
    store_id = session.get("store_id")
    if request.method == "POST":
        name = request.form.get("name")
        price = float(request.form.get("price", 0))
        desc = request.form.get("description")
        data = {"name": name, "price": price, "desc_ai": desc}
        MerchantService.create_product(store_id, data)
        flash("Product added", "success")
        return redirect("/inventory")
        
    products = MerchantService.get_products(store_id)
    return render_template("inventory.html", products=products)

# ================================
# CHECKOUT ROUTE
# ================================
@merchant_bp.route("/checkout/<int:order_id>")
def checkout(order_id):
    order = MerchantService.get_order(order_id)
    if not order:
        return "Order not found", 404
    store = MerchantService.get_store(order.store_id)
    return render_template("checkout.html", order=order, store=store)

