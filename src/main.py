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
app.register_blueprint(chat_bp)

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
        email = request.form.get("email")
        password = request.form.get("password")
        
        db = SessionLocal()
        try:
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
    try:
        store = db.query(Store).filter_by(id=session["store_id"]).first()
        total_chats = db.query(func.count(Conversation.id)).filter_by(store_id=store.id).scalar() or 0
        successful_sales = db.query(func.count(Order.id)).filter_by(store_id=store.id, status='paid').scalar() or 0
        revenue = db.query(func.sum(Order.total_amount)).filter_by(store_id=store.id, status='paid').scalar() or 0
        
        return render_template("dashboard.html", store=store, total_chats=total_chats, 
                               successful_sales=successful_sales, revenue=revenue, 
                               redis_conn_status=True)
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

        try:
            active_stores = db.query(func.count(Store.id)).filter_by(status='active').scalar() or 0
            total_revenue = db.query(func.sum(Store.plan_price)).scalar() or 0
            total_stores = db.query(func.count(Store.id)).scalar() or 0
            overdue_stores = db.query(func.count(Store.id)).filter_by(payment_status='overdue').scalar() or 0
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
    try:
        store = db.query(Store).filter_by(id=store_id).first()
        if not store:
            flash("Store not found", "error")
            return redirect("/admin/stores")
            
        if request.method == "POST":
            # Update store status / admin overrides
            action = request.form.get("action")
            if action == "suspend":
                store.status = "suspended"
                store.is_active = False
            elif action == "activate":
                store.status = "active"
                store.is_active = True
            elif action == "delete":
                db.delete(store)
                db.commit()
                flash("Store deleted", "success")
                return redirect("/admin/stores")
                
            db.commit()
            flash(f"Store {store.name} updated", "success")
            return redirect(f"/admin/store/{store_id}")
            
        return render_template("admin_store_detail.html", store=store)
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
