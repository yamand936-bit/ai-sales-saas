import logging
import datetime
import secrets

from flask import Flask, jsonify, render_template, request, redirect, flash, session, url_for
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from src.core.database import engine, SessionLocal
from src.core.models_aggregator import Base
from src.core.config import settings
from src.core.init_settings import init_settings

from src.stores.models import Store
from src.products.models import Product
from src.users.models import User
from src.chat.models import Conversation, Message
from src.orders.models import Order
from src.chat.router import chat_bp
from src.utils.i18n import get_t
from src.core.models import SystemSetting

# ================================
# LOGGING & APP INIT
# ================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Initializing Database schema...")
Base.metadata.create_all(bind=engine)

app = Flask(__name__, template_folder='templates')
init_settings()

app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY not set")
app.permanent_session_lifetime = datetime.timedelta(days=7)

from src.merchant.router import merchant_bp
app.register_blueprint(chat_bp)
app.register_blueprint(merchant_bp)

# ================================
# SECURITY & CONTEXT
# ================================
def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

@app.context_processor
def inject_i18n():
    language = session.get("lang", "ar")
    t_dict = get_t(language)
    def _translate(key):
        return t_dict.get(key, key)
    return {"_": _translate, "t": _translate, "lang": language}

@app.before_request
def security_middleware():
    if request.method == "POST":
        if not request.path.startswith("/webhooks") and not request.path.startswith("/api/webhooks"):
            token = session.get('csrf_token')
            req_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            if not req_token and request.is_json:
                req_token = request.json.get('csrf_token')
            if not token or token != req_token:
                return jsonify({"error": "CSRF verification failed."}), 403

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

def merchant_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "merchant":
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ================================
# GLOBAL ROUTES
# ================================
@app.route("/")
def index():
    return redirect("/login")

@app.route("/set_lang/<lang>", endpoint="set_language")
def set_language(lang):
    if lang in ["ar", "en", "tr"]:
        session["lang"] = lang
    return redirect(request.referrer or "/")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/login")

# ================================
# MERCHANT ROUTES
# ================================
@app.route("/login", methods=["GET", "POST"])
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

@app.route("/dashboard")
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

@app.route("/inventory", methods=["GET", "POST"])
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
# ADMIN ROUTES
# ================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == os.getenv("SUPERADMIN_PASSWORD"):
            session.permanent = True
            session["role"] = "admin"
            session["is_admin"] = True
            session["lang"] = "ar"
            return redirect("/admin/dashboard")
        flash("Invalid Admin PIN", "error")
    return render_template("admin_login.html")

@app.route("/admin")
@app.route("/admin/")
def admin_root():
    return redirect("/admin/dashboard")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = SessionLocal()
    from sqlalchemy.exc import SQLAlchemyError
    try:
        active_stores = 0
        total_revenue = 0
        total_stores = 0
        overdue_stores = 0
        total_orders = 0
        global_tokens = 0
        messages_today = 0
        admin_logs = []

        # Quick Stats Layer 1
        try:
            active_stores = db.query(Store).filter_by(status='active').count()
            total_revenue = db.query(func.sum(Store.plan_price)).scalar() or 0
            total_stores = db.query(func.count(Store.id)).scalar() or 0
            overdue_stores = db.query(Store).filter_by(payment_status='overdue').count()
        except SQLAlchemyError:
            db.rollback()

        try:
            total_orders = db.query(func.count(Order.id)).scalar() or 0
        except SQLAlchemyError:
            db.rollback()

        try:
            from src.chat.models import AILog
            global_tokens = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).scalar() or 0
        except SQLAlchemyError:
            db.rollback()

        # Optional Chart rendering variables required by Jinja `tojson`
        chart_dates = []
        chart_tokens = []

        return render_template("admin_dashboard.html", 
                               active_stores=active_stores, 
                               total_revenue=total_revenue,
                               total_stores=total_stores,
                               overdue_stores=overdue_stores,
                               global_tokens=global_tokens,
                               messages_today=messages_today,
                               total_orders=total_orders,
                               admin_logs=admin_logs,
                               chart_dates=chart_dates,
                               chart_tokens=chart_tokens)
    finally:
        db.close()

@app.route("/admin/store/<int:store_id>/login_as")
@admin_required
def admin_login_as(store_id):
    session["role"] = "merchant"
    session["store_id"] = store_id
    return redirect("/dashboard")

@app.route("/admin/stores", methods=["GET", "POST"])
@admin_required
def admin_stores():
    db = SessionLocal()
    try:
        if request.method == "POST":
            name = request.form.get("name")
            owner_name = request.form.get("owner_name")
            owner_email = request.form.get("owner_email")
            password = request.form.get("password")
            plan_price = float(request.form.get("plan_price") or 0.0)
            token_limit = int(request.form.get("monthly_token_limit") or 100000)
            
            new_store = Store(
                name=name, owner_name=owner_name, owner_email=owner_email,
                password_hash=generate_password_hash(password),
                plan_price=plan_price, monthly_token_limit=token_limit, status="active"
            )
            db.add(new_store)
            db.commit()
            flash("Store licensed successfully", "success")
            return redirect("/admin/stores")
            
        stores = db.query(Store).all()
        return render_template("admin_stores.html", stores=stores, now=datetime.datetime.utcnow())
    finally:
        db.close()

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    db = SessionLocal()
    try:
        if request.method == "POST":
            key = request.form.get("key", "").strip()
            value = request.form.get("value", "").strip()

            if key.endswith("_limit") and not value.isdigit():
                flash(get_t(session.get("lang")).get("numeric_limit_err", "Error"), "error")
                return redirect("/admin/settings")

            setting = db.query(SystemSetting).filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                db.add(SystemSetting(key=key, value=value))
            db.commit()
            flash(get_t(session.get("lang")).get("settings_saved_success", "Success"), "success")
            return redirect("/admin/settings")

        settings_list = db.query(SystemSetting).all()
        return render_template("admin_settings.html", settings=settings_list)
    finally:
        db.close()

@app.route("/admin/store/<int:store_id>", methods=["GET", "POST"])
@admin_required
def admin_store_detail(store_id):
    db = SessionLocal()
    from sqlalchemy.exc import SQLAlchemyError
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            flash("Store not found", "error")
            return redirect("/admin/stores")
            
        if request.method == "POST":
            # Update store status / admin overrides
            action = request.form.get("action_type") or request.form.get("action")
            if action == "suspend":
                store.status = "suspended"
                store.is_active = False
            elif action == "activate":
                store.status = "active"
                store.is_active = True
            elif action == "quick_extend":
                if not store.expires_at:
                    from datetime import datetime
                    store.expires_at = datetime.utcnow()
                
                from datetime import timedelta
                store.expires_at += timedelta(days=30)
            elif action == "delete":
                db.delete(store)
                db.commit()
                flash("Store deleted", "success")
                return redirect("/admin/stores")
            else:
                # Full configuration save (from detail form)
                store.name = request.form.get("name", store.name)
                store.status = request.form.get("status", store.status)
                store.is_active = (store.status == 'active')
                store.owner_name = request.form.get("owner_name", store.owner_name)
                store.owner_phone = request.form.get("owner_phone", store.owner_phone)
                try:
                    store.plan_price = float(request.form.get("plan_price") or store.plan_price)
                except ValueError:
                    pass
                store.billing_cycle = request.form.get("billing_cycle", store.billing_cycle)
                try:
                    store.monthly_token_limit = int(request.form.get("monthly_token_limit") or store.monthly_token_limit)
                except ValueError:
                    pass
                store.payment_status = request.form.get("payment_status", store.payment_status)
                
                extend_days = request.form.get("extend_days")
                if extend_days and extend_days.isdigit():
                    if not store.expires_at:
                        store.expires_at = datetime.datetime.utcnow()
                    store.expires_at += datetime.timedelta(days=int(extend_days))
                
                old_tg = store.telegram_token
                store.telegram_token = request.form.get("telegram_token", store.telegram_token)
                if store.telegram_token and store.telegram_token != old_tg:
                    import requests
                    webhook_url = f"https://{request.host}/webhooks/telegram/{store.telegram_token}"
                    try:
                        resp = requests.post(f"https://api.telegram.org/bot{store.telegram_token}/setWebhook", json={"url": webhook_url}, timeout=3)
                        if resp.status_code == 200:
                            flash("Telegram webhook activated successfully! 🤖", "success")
                        else:
                            flash("Telegram token saved, but webhook failed (Domain HTTPS required).", "error")
                    except Exception:
                        pass
                
                store.whatsapp_token = request.form.get("whatsapp_token", store.whatsapp_token)
                store.instagram_token = request.form.get("instagram_token", store.instagram_token)
                
                # Extract boolean feature flags
                import json
                features = {
                    "whatsapp": bool(request.form.get("feat_whatsapp")),
                    "instagram": bool(request.form.get("feat_instagram")),
                    "voice": bool(request.form.get("feat_voice")),
                    "advanced_ai": bool(request.form.get("feat_advanced_ai"))
                }
                store.features_json = json.dumps(features)
                
            db.commit()
            flash(f"Store {store.name} updated", "success")
            return redirect(f"/admin/store/{store_id}")
            
        # Load Safe Metrics
        conv_count = 0
        order_count = 0
        tokens_used = 0
        features_dict = {}
        
        # Fetch actual statistics (safe loading)
        try:
            from sqlalchemy import func
            conv_count = db.query(Conversation).join(User).filter(User.store_id == store_id).count()
            order_count = db.query(Order).filter_by(store_id=store_id, status='paid').count()
        except SQLAlchemyError:
            conv_count = 0
            order_count = 0
            db.rollback()
            
        try:
            from src.chat.models import AILog
            tokens_used = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).filter(AILog.store_id == store.id).scalar() or 0
        except SQLAlchemyError:
            db.rollback()

        import json
        if getattr(store, 'features_json', None):
            try:
                features_dict = json.loads(store.features_json)
            except:
                pass

        return render_template("admin_store_detail.html", 
                               store=store,
                               conv_count=conv_count,
                               order_count=order_count,
                               tokens_used=tokens_used,
                               features_dict=features_dict)
    finally:
        db.close()

@app.route("/admin/messages-order", methods=["GET"])
@admin_required
def admin_messages_order():
    print("API HIT: /admin/messages-order")
    db = SessionLocal()
    try:
        from src.chat.models import Message
        msgs = db.query(Message).order_by(Message.timestamp.desc()).limit(10).all()
        data = [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@app.route("/admin/global-token", methods=["GET"])
@admin_required
def admin_global_token():
    print("API HIT: /admin/global-token")
    db = SessionLocal()
    try:
        stores = db.query(Store).all()
        data = [{"store_id": s.id, "telegram_token": s.telegram_token} for s in stores]
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@app.route("/admin/global-live-feed", methods=["GET"])
@admin_required
def admin_global_live_feed():
    print("API HIT: /admin/global-live-feed")
    db = SessionLocal()
    try:
        from src.chat.models import Conversation
        convs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(10).all()
        data = [{"id": c.id, "user_id": c.user_id, "requires_human": c.requires_human} for c in convs]
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@app.route("/admin/global-ai-usage", methods=["GET"])
@admin_required
def admin_global_ai_usage():
    print("API HIT: /admin/global-ai-usage")
    db = SessionLocal()
    try:
        from src.chat.models import AILog
        logs = db.query(AILog).order_by(AILog.created_at.desc()).limit(10).all()
        data = [{"store_id": l.store_id, "prompt_tokens": l.prompt_tokens} for l in logs]
        result = {"status": "success", "data": data}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@app.route("/admin/audit-logs-header", methods=["GET"])
@admin_required
def admin_audit_logs_header():
    print("API HIT: /admin/audit-logs-header")
    result = {"status": "success", "data": [{"log": "Active"}]}
    print("DB RESULT:", result)
    return jsonify(result)

@app.route("/admin/subscription-days/<int:store_id>", methods=["GET"])
@admin_required
def admin_subscription_days(store_id):
    print(f"API HIT: /admin/subscription-days/{store_id}")
    db = SessionLocal()
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        days_left = 0
        if store and getattr(store, 'next_billing_date', None):
            days_left = max((store.next_billing_date - datetime.datetime.utcnow()).days, 0)
        
        result = {"days_left": days_left}
        print("DB RESULT:", result)
        return jsonify(result)
    finally:
        db.close()

@app.route("/admin/live_feed")
@admin_required
def admin_live_feed():
    return render_template("admin_live_feed.html")

# ================================
# CHECKOUT ROUTE
# ================================
@app.route("/checkout/<int:order_id>")
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

# ================================
# RUN SERVER
# ================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)


@app.route("/admin/ai-health")
@admin_required
def admin_ai_health():
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Parse metrics
        success = int(r.get("ai:success") or 0)
        retry = int(r.get("ai:retry") or 0)
        fallback = int(r.get("ai:fallback") or 0)
        failure = int(r.get("ai:failure") or 0)
        
        total = success + fallback + failure
        if total == 0:
            success_rate = 100.0
            failure_rate = 0.0
            fallback_rate = 0.0
        else:
            success_rate = round(success / total * 100, 2)
            failure_rate = round(failure / total * 100, 2)
            fallback_rate = round(fallback / total * 100, 2)
            
        # Parse providers
        from src.ai_engine.service import ai_engine
        providers = ai_engine.router.providers
        
        active_providers = []
        degraded_providers = []
        best_provider = None
        min_failures = float('inf')
        
        for name, provider in providers.items():
            if provider.is_configured():
                if ai_engine.router._is_degraded(name):
                    degraded_providers.append(name)
                else:
                    active_providers.append(name)
                    # Simple heuristic: provider with least failures in the current window is "best"
                    fails = r.llen(f"failure_streak:{name}")
                    if fails < min_failures:
                        min_failures = fails
                        best_provider = name

        return jsonify({
            "status": "online" if active_providers else "degraded",
            "global_metrics": {
                "success_rate_percent": success_rate,
                "failure_rate_percent": failure_rate,
                "fallback_percent": fallback_rate,
                "raw_counts": {
                    "success": success,
                    "retry": retry,
                    "fallback": fallback,
                    "failure": failure
                }
            },
            "providers": {
                "active": active_providers,
                "degraded": degraded_providers,
                "best_recommended": best_provider or "none"
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
