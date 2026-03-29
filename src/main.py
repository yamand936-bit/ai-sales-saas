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

app.secret_key = "super_secret_enterprise_key"
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
        if session.get("role") != "admin":
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

@app.route("/logout")
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
        total_orders = db.query(Order).filter_by(store_id=store.id, status='paid').count()
        revenue = db.query(func.sum(Order.total_amount)).filter(Order.store_id == store.id, Order.status == 'paid').scalar() or 0
        conversion_rate = round((total_orders / total_conversations * 100), 1) if total_conversations > 0 else 0

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
                               chart_dates=[],
                               chart_tokens=[],
                               conversations=conversations,
                               human_requests=human_requests,
                               products=products,
                               orders=orders,
                               users=users,
                               revenue=revenue)
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
        if password == "superadmin123":  # Ideally moved to env vars
            session.permanent = True
            session["role"] = "admin"
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
        return render_template("admin_stores.html", stores=stores)
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
                if store.expires_at:
                    store.expires_at += datetime.timedelta(days=30)
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
