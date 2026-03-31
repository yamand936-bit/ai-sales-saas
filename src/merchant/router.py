from werkzeug.security import check_password_hash
from src.api.middlewares import merchant_required
from flask import Blueprint, request, jsonify, render_template, redirect, session, flash, current_app, Response
from sqlalchemy import func
import json
import datetime

from src.core.database import SessionLocal
from src.stores.models import Store
from src.products.models import Product
from src.orders.models import Order
from src.chat.models import Conversation, Message, AILog
from src.users.models import User
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
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if store:
            store.ai_mode = request.form.get("ai_mode", store.ai_mode)
            store.ai_tone = request.form.get("ai_tone", store.ai_tone)
            store.policy = request.form.get("policy", store.policy)
            db.commit()
            flash("Settings saved!", "success")
        return redirect("/dashboard")
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/broadcast", methods=["POST"])
@merchant_required
def send_broadcast(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    msg = request.json.get("message") if request.is_json else request.form.get("message")
    from src.chat.tasks import send_telegram_message
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if store and store.telegram_token and msg:
            users = db.query(User).filter_by(store_id=store_id).all()
            for u in users:
                if u.telegram_id:
                    send_telegram_message.delay(store.telegram_token, u.telegram_id, msg)
            flash(f"Broadcast sent to {len(users)} users!", "success")
        return redirect("/dashboard")
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/order/<int:order_id>/approve", methods=["POST"])
@merchant_required
def approve_order(store_id, order_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    try:
        MerchantService.update_order_status(order_id, "paid")
        flash("Order approved!", "success")
    except Exception:
        pass # Handle if order is None per simplified service
    return redirect("/dashboard")

@merchant_bp.route("/api/merchant/<int:store_id>/messages/<int:user_id>", methods=["GET"])
@merchant_required
def get_messages(store_id, user_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id, store_id=store_id).first()
        if not user: return jsonify({"messages": []})
        conv = db.query(Conversation).filter_by(user_id=user_id).first()
        if not conv:
            return jsonify({"messages": []})
        msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.timestamp).all()
        return jsonify({"messages": [{"role": m.role, "content": m.content, "time": m.timestamp.strftime('%H:%M')} for m in msgs[-50:]]})
    finally:
        db.close()

@merchant_bp.route("/merchant/conversations", methods=["GET"])
@merchant_required
def merchant_conversations_endpoint():
    print("API HIT: /merchant/conversations")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    db = SessionLocal()
    try:
        users = db.query(User).filter_by(store_id=store_id).all()
        user_ids = [u.id for u in users]
        convs = db.query(Conversation).filter(Conversation.user_id.in_(user_ids)).all()
        
        data = []
        for conv in convs:
            last_msg = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.timestamp.desc()).first()
            data.append({
                "user_id": conv.user_id,
                "name": conv.user.first_name,
                "phone": conv.user.phone,
                "last_message": last_msg.content if last_msg else None,
                "last_message_time": last_msg.timestamp.strftime('%H:%M') if last_msg else None
            })
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@merchant_bp.route("/merchant/users", methods=["GET"])
@merchant_required
def merchant_users_endpoint():
    print("API HIT: /merchant/users")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    db = SessionLocal()
    try:
        users = db.query(User).filter_by(store_id=store_id).all()
        data = [{"id": u.id, "name": u.first_name, "telegram_id": u.telegram_id} for u in users]
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/toggle_ai/<int:user_id>", methods=["POST"])
@merchant_required
def toggle_ai(store_id, user_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id, store_id=store_id).first()
        if not user: return redirect("/dashboard")
        conv = db.query(Conversation).filter_by(user_id=user_id).first()
        if conv:
            conv.requires_human = not conv.requires_human
            db.commit()
        return redirect("/dashboard")
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/toggle_system_ai", methods=["POST"])
@merchant_required
def toggle_system_ai(store_id):
    if store_id != session.get("store_id"): return jsonify({"error": "Forbidden"}), 403
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if store:
            store.ai_enabled = not store.ai_enabled
            db.commit()
            return jsonify({"status": "success", "ai_enabled": store.ai_enabled})
        return jsonify({"error": "Store not found"}), 404
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/reply/<telegram_id>", methods=["POST"])
@merchant_required
def merchant_reply(store_id, telegram_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    from src.chat.service import send_telegram_msg
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        user = db.query(User).filter_by(telegram_id=telegram_id, store_id=store_id).first()
        if not store or not user:
            return jsonify({"error": "Not found"}), 404
            
        action_val = request.form.get("action_val")
        reply_msg = request.form.get("reply_msg")
        
        conv = db.query(Conversation).filter_by(user_id=user.id).first()
        
        if reply_msg:
            send_telegram_msg(store.telegram_token, telegram_id, reply_msg)
            if conv:
                new_msg = Message(conversation_id=conv.id, role="assistant", content=reply_msg)
                db.add(new_msg)
                
        if action_val == 'resolve' and conv:
            conv.requires_human = False
            
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

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
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=session["store_id"]).first()
        openai.api_key = settings.OPENAI_API_KEY
        sys_msg = f"You are an AI assistant for {store.name}. Tone: {getattr(store, 'ai_tone', 'friendly')}. Focus: {getattr(store, 'ai_mode', 'sales')}."
        
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt}
                ]
            )
            reply = response.choices[0].message.content
            return jsonify({"success": True, "reply": reply})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/auto_followup", methods=["POST"])
@merchant_required
def auto_followup(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
        from src.chat.service import send_telegram_msg
        from src.ai_engine.service import ai_engine
        import json
        
        store = db.query(Store).filter_by(id=store_id, status='active').first()
        if not store or not getattr(store, "ai_enabled", True): 
            return jsonify({"status": "error", "message": "Store AI inactive"}), 400

        import logging
        logger = logging.getLogger(__name__)

        try:
            feats = json.loads(store.features) if store.features else {}
            delay_mins = int(feats.get("followup_delay", 60))
        except Exception:
            delay_mins = 60
            
        delay_mins = max(30, delay_mins) # Task 2: minimum 30 minutes cooldown
        cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=delay_mins)

        conversations = db.query(Conversation).join(User).filter(User.store_id == store.id).all()
        follow_ups_sent = 0

        for conv in conversations:
            ctx = {}
            if conv.context:
                try:
                    ctx = json.loads(conv.context)
                except Exception: pass
            
            if ctx.get("auto_followed_up_at"):
                logger.info(f"AFU Skip Conv {conv.id}: Already followed up.")
                continue
                
            msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.timestamp).all()
            
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

            msg_ai = Message(conversation_id=conv.id, role="assistant", content=reply)
            db.add(msg_ai)
            
            ctx["auto_followed_up_at"] = datetime.datetime.utcnow().isoformat()
            ctx["follow_up_sent"] = True
            conv.context = json.dumps(ctx)
            db.commit()
            
            if conv.channel == "telegram" and getattr(store, "telegram_token", None) and getattr(conv.user, "telegram_id", None):
                send_telegram_msg(store.telegram_token, conv.user.telegram_id, reply)
                
            follow_ups_sent += 1

        return jsonify({"status": "success", "sent": follow_ups_sent, "delay_mins": delay_mins})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()



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
        
        db = SessionLocal()
        try:
            store = None
            if store_id.isdigit():
                store = db.query(Store).filter_by(id=int(store_id)).first()
            elif store_id:
                store = db.query(Store).filter_by(owner_email=store_id).first()
            elif email:
                 store = db.query(Store).filter_by(owner_email=email).first()
                 
            if store and check_password_hash(store.password_hash, password):
                session.permanent = True
                session["role"] = "merchant"
                session["store_id"] = store.id
                session["lang"] = "ar"
                return redirect("/dashboard")
            flash("Invalid email or password", "error")
        finally:
            db.close()
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
    db = SessionLocal()
    try:
        order = db.query(Order).filter_by(id=order_id).first()
        if not order:
            return "Order not found", 404
        store = db.query(Store).filter_by(id=order.store_id).first()
        return render_template("checkout.html", order=order, store=store)
    finally:
        db.close()

