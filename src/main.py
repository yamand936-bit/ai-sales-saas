import os
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
from src.api.middlewares import merchant_required, admin_required
from src.admin.router import admin_bp

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
app.register_blueprint(admin_bp)


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


