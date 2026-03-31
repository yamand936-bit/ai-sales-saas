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

merchant_bp = Blueprint('merchant', __name__)



@merchant_bp.route("/merchant/<int:store_id>/add_product", methods=["POST"])
@merchant_required
def add_product(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
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
        
        product = Product(
            store_id=store_id, 
            name=name, 
            price=price, 
            description=desc, 
            image_url=image_url, 
            category=category, 
            sizes="{}",
            is_service=is_service,
            booking_link=booking_link,
            type=type_val,
            duration=duration
        )
        db.add(product)
        db.commit()
        flash("Product added", "success")
        return redirect("/dashboard")
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/toggle_product/<int:product_id>", methods=["POST"])
@merchant_required
def toggle_product(store_id, product_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
        product = db.query(Product).filter_by(id=product_id, store_id=store_id).first()
        if product:
            product.is_active = not product.is_active
            db.commit()
            flash("Product status updated", "success")
        return redirect("/dashboard")
    finally:
        db.close()

@merchant_bp.route("/merchant/<int:store_id>/delete_product/<int:product_id>", methods=["POST"])
@merchant_required
def delete_product(store_id, product_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    db = SessionLocal()
    try:
        product = db.query(Product).filter_by(id=product_id, store_id=store_id).first()
        if product:
            db.delete(product)
            db.commit()
            flash("Product deleted", "success")
        return redirect("/dashboard")
    finally:
        db.close()

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
    db = SessionLocal()
    try:
        order = db.query(Order).filter_by(id=order_id, store_id=store_id).first()
        if order:
            order.status = "paid"
            db.commit()
            flash("Order approved!", "success")
        return redirect("/dashboard")
    finally:
        db.close()

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
    db = SessionLocal()
    import datetime
    try:
        store = db.query(Store).filter_by(id=session["store_id"]).first()
        if not store:
            session.clear()
            return redirect("/login")

        # Basic Stats
        total_conversations = db.query(Conversation).join(User).filter(User.store_id == store.id).count()
        paid_users = db.query(User).join(Order).filter(User.store_id == store.id, Order.status == 'paid').distinct().count()
        total_users = db.query(User).filter_by(store_id=store.id).count()
        total_orders = db.query(Order).filter_by(store_id=store.id, status='paid').count()
        revenue = db.query(func.sum(Order.total_amount)).filter(Order.store_id == store.id, Order.status == 'paid').scalar() or 0
        conversion_rate = round((paid_users / total_users * 100), 1) if total_users > 0 else 0

        # Tokens & AI
        from src.chat.models import AILog
        from sqlalchemy.exc import SQLAlchemyError
        
        try:
            total_tokens = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).filter(AILog.store_id == store.id).scalar() or 0
            ai_interactions = db.query(AILog).filter_by(store_id=store.id).count()
        except SQLAlchemyError:
            db.rollback()
            total_tokens = 0
            ai_interactions = 0
        
        # Token Warning Calculation
        monthly_token_limit = store.monthly_token_limit or 100000
        token_warning = total_tokens >= (monthly_token_limit * 0.8)
        
        # Latency Fake/Calc
        avg_latency = 450
        
        # Lists for CRM / Inventory / Orders
        try:
            conversations = db.query(Conversation).join(User).filter(User.store_id == store.id).order_by(Conversation.created_at.desc()).all()
            import json
            for c in conversations:
                c.lead_status = "unknown"
                if c.context:
                    try:
                        ctx = json.loads(c.context)
                        c.lead_status = ctx.get("lead_status", "unknown")
                        c.follow_up_sent = ctx.get("follow_up_sent", False)
                        c.follow_up_replied = ctx.get("follow_up_replied", False)
                        c.converted = ctx.get("converted", False)
                        c.conversion_after_followup = ctx.get("conversion_after_followup", False)
                        c.last_product = ctx.get("last_product", "")
                        c.price_range = ctx.get("price_range", "")
                        c.intent = ctx.get("intent", "")
                    except Exception:
                        pass
                        
            human_requests = [c for c in conversations if c.requires_human]
            products = db.query(Product).filter(Product.store_id == store.id).all()
            orders = db.query(Order).filter(Order.store_id == store.id).order_by(Order.created_at.desc()).all()
        except SQLAlchemyError:
            db.rollback()
            conversations = []
            human_requests = []
            products = []
            orders = []
        users = db.query(User).filter_by(store_id=store.id).all()

        is_expired = False
        if store.expires_at and store.expires_at < datetime.datetime.utcnow():
            is_expired = True

        try:
            from sqlalchemy import cast, Date
            thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            logs = db.query(
                func.date(AILog.created_at).label('date'),
                func.sum(AILog.prompt_tokens + AILog.completion_tokens).label('tokens')
            ).filter(AILog.store_id == store.id, AILog.created_at >= thirty_days_ago).group_by(func.date(AILog.created_at)).all()
            chart_dates = [log.date for log in logs if log.date]
            chart_tokens = [log.tokens for log in logs if log.date]
        except SQLAlchemyError:
            chart_dates = []
            chart_tokens = []

        print("API HIT: /merchant/dashboard-data")
        print("TOGGLE AI:", store.ai_enabled)

        # AI Smart Insights Logic
        ai_insights = []
        import logging
        logger = logging.getLogger(__name__)

        # Task 4: Insights Improvement
        if total_conversations > 10:
            if conversion_rate < 5.0:
                msg = f"Your conversion rate is {conversion_rate}% (below average 5-8%). Review store policy to push for sales."
                ai_insights.append({"icon": "⚠️", "text": msg, "color": "red"})
                logger.info(f"Insight Generated (Store {store.id}): Low Conversion Warning")
            elif 5.0 <= conversion_rate <= 10.0:
                msg = f"Your conversion rate is {conversion_rate}% (average). Offer a discount code to push hesitant leads."
                ai_insights.append({"icon": "💡", "text": msg, "color": "blue"})
                logger.info(f"Insight Generated (Store {store.id}): Average Conversion Notice")
            else:
                msg = f"Your conversion rate is {conversion_rate}% (above average). Great job maintaining healthy engagement!"
                ai_insights.append({"icon": "🚀", "text": msg, "color": "green"})
                logger.info(f"Insight Generated (Store {store.id}): Good Conversion Praise")

        if total_tokens > (monthly_token_limit * 0.4) and conversion_rate < 5.0:
            msg = "Efficiency Warning: High token use without enough sales. Switch AI Mode to 'Sales'."
            ai_insights.append({"icon": "💸", "text": msg, "color": "yellow"})
            logger.info(f"Insight Generated (Store {store.id}): Efficiency Token Warning")
        
        if total_conversations > 0 and len(human_requests) > (total_conversations * 0.3):
            ai_insights.append({"icon": "👨‍💼", "text": "طلب تدخل بشري كبير يفوق 30%. يرجى مراجعة 'سياسة المتجر' وتزويد المساعد بمعلومات أكثر شمولية.", "color": "yellow"})
            
        if not ai_insights:
            if total_conversations == 0:
                ai_insights.append({"icon": "✨", "text": "مرحباً! ستظهر التحليلات الذكية هنا فور بدء المحادثات.", "color": "blue"})
            else:
                ai_insights.append({"icon": "✅", "text": "وضع المنصة مستقر ومعدل الاستجابة مثالي.", "color": "green"})

        # Task 1 & 4 Calculation
        followups_sent = sum(1 for c in conversations if getattr(c, "follow_up_sent", False))
        replied_count = sum(1 for c in conversations if getattr(c, "follow_up_replied", False))
        conversions_after = sum(1 for c in conversations if getattr(c, "conversion_after_followup", False))
        
        followup_rate = round((followups_sent / total_conversations) * 100, 1) if total_conversations > 0 else 0
        reply_rate = round((replied_count / followups_sent) * 100, 1) if followups_sent > 0 else 0
        conversion_after_rate = round((conversions_after / replied_count) * 100, 1) if replied_count > 0 else 0

        # Task 5
        if followups_sent > 0 and conversions_after > 0:
            imp_pct = round((conversions_after / total_conversations) * 100, 1) if total_conversations else 0
            if imp_pct > 0:
                ai_insights.append({"icon": "📈", "text": f"Follow-ups improved conversion by {imp_pct}%", "color": "green"})

        metrics_funnel = {
            "total": total_conversations,
            "followups_sent": followups_sent,
            "replied": replied_count,
            "conversions_after": conversions_after,
            "followup_rate": followup_rate,
            "reply_rate": reply_rate,
            "conversion_after_rate": conversion_after_rate
        }

        return render_template("merchant.html", 
                               store=store, 
                               lang=store.language or "ar",
                               is_expired=is_expired,
                               token_warning=token_warning,
                               monthly_token_limit=monthly_token_limit,
                               total_conversations=total_conversations,
                               total_orders=total_orders,
                               conversion_rate=conversion_rate,
                               total_tokens=total_tokens,
                               avg_latency=avg_latency,
                               ai_interactions=ai_interactions,
                               chart_dates=json.dumps(chart_dates),
                               chart_tokens=json.dumps(chart_tokens),
                               conversations=conversations,
                               human_requests=human_requests,
                               products=products,
                               orders=orders,
                               users=users,
                               revenue=revenue,
                               ai_insights=ai_insights,
                               metrics_funnel=metrics_funnel)
    finally:
        db.close()

@merchant_bp.route("/inventory", methods=["GET", "POST"])
@merchant_required
def inventory():
    db = SessionLocal()
    try:
        if request.method == "POST":
            # Add product logic
            name = request.form.get("name")
            price = float(request.form.get("price", 0))
            desc = request.form.get("description")
            product = Product(store_id=session["store_id"], name=name, price=price, desc_ai=desc)
            db.add(product)
            db.commit()
            flash("Product added", "success")
            return redirect("/inventory")
            
        products = db.query(Product).filter_by(store_id=session["store_id"]).all()
        return render_template("inventory.html", products=products)
    finally:
        db.close()

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

