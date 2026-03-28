# ================================

# IMPORTS (MUST BE TOP)

# ================================

import logging
import datetime
import json
import secrets

from flask import Flask, jsonify, render_template, request, redirect, flash, session, url_for, Response, stream_with_context
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from src.core.database import engine, SessionLocal
from src.core.models_aggregator import Base
from src.core.config import settings
from src.core.events import publish_event
from src.core.init_settings import init_settings

from src.stores.models import Store
from src.products.models import Product
from src.users.models import User
from src.chat.models import Conversation, Message, AILog
from src.chat.router import chat_bp

from src.utils.i18n import get_t

import redis

# ================================

# LOGGING + DB INIT

# ================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

logger.info("Initializing Database schema...")
Base.metadata.create_all(bind=engine)

# ================================

# FLASK APP

# ================================

app = Flask(**name**, template_folder='templates')

init_settings()

app.secret_key = "super_secret_enterprise_key"

app.config.update(
SESSION_COOKIE_SAMESITE="Lax",
SESSION_COOKIE_SECURE=False,
SESSION_COOKIE_HTTPONLY=True,
SESSION_PERMANENT=False
)

app.permanent_session_lifetime = datetime.timedelta(days=7)
app.register_blueprint(chat_bp)

# ================================

# CSRF

# ================================

def generate_csrf_token():
if 'csrf_token' not in session:
session['csrf_token'] = secrets.token_hex(32)
return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

@app.before_request
def security_middleware():
if request.method == "POST":
if not request.path.startswith("/webhooks"):
token = session.get('csrf_token')
req_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')

```
        if not token or token != req_token:
            return jsonify({"error": "CSRF verification failed."}), 403
```

# ================================

# AUTH DECORATORS

# ================================

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

# ADMIN SETTINGS (FIXED)

# ================================

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
from src.core.models import SystemSetting

```
db = SessionLocal()

try:
    if request.method == "POST":
        key = request.form.get("key", "").strip()
        value = request.form.get("value", "").strip()

        if key.endswith("_limit") and not value.isdigit():
            flash("Limit must be numeric", "error")
            return redirect("/admin/settings")

        setting = db.query(SystemSetting).filter_by(key=key).first()

        if setting:
            setting.value = value
        else:
            db.add(SystemSetting(key=key, value=value))

        db.commit()
        flash("Saved successfully", "success")
        return redirect("/admin/settings")

    settings = db.query(SystemSetting).all()
    return render_template("admin_settings.html", settings=settings)

finally:
    db.close()
```

# ================================

# LANGUAGE

# ================================

@app.route("/set_lang/<lang>", endpoint="set_language")
def set_language(lang):
if lang in ["ar", "en", "tr"]:
session["lang"] = lang
return redirect(request.referrer or "/")

# ================================

# BASIC ROUTES

# ================================

@app.route("/")
def index():
return redirect("/login")

@app.route("/logout")
def logout():
session.clear()
return redirect("/login")

# ================================

# RUN

# ================================

if **name** == "**main**":
app.run(host="0.0.0.0", port=8080)
