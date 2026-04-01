import os
import logging
import datetime
import secrets

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[FlaskIntegration(), CeleryIntegration()],
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    send_default_pii=True,
)

from flask import Flask, jsonify, render_template, request, redirect, flash, session, url_for
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from src.core.database import engine, SessionLocal, Base
from src.core.config import settings
from src.api.middlewares import merchant_required, admin_required
from src.admin.router import admin_bp


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

try:
    from src.core.feature_service import FeatureService
    FeatureService.initialize_defaults()
except Exception as e:
    logger.warning(f"Could not initialize default feature flags: {e}")

app = Flask(__name__, template_folder='templates')

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY not set")

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)
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
# RUN SERVER
# ================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)


