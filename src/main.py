import logging
import datetime
import json

from flask import Flask, jsonify, render_template, request, redirect, flash, session, url_for, Response, stream_with_context
from sqlalchemy import func

from src.core.database import engine, SessionLocal
from src.stores.models import Store
from src.products.models import Product
from src.users.models import User
from src.chat.models import Conversation, Message, AILog
from src.core.models_aggregator import Base
from src.chat.router import chat_bp
from src.utils.i18n import get_t
from src.core.events import publish_event
from src.core.config import settings

import redis

# ================================
# INIT APP
# ================================
app = Flask(__name__, template_folder='templates')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================================
# INIT DB
# ================================
logger.info("Initializing Database schema...")
Base.metadata.create_all(bind=engine)

# ================================
# REGISTER BLUEPRINTS
# ================================
app.register_blueprint(chat_bp)

# ================================
# ROUTES
# ================================

@app.route("/")
def home():
    return "AI Sales SaaS is running 🚀"


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    db = SessionLocal()

    if request.method == "POST":
        key = request.form.get("key")
        value = request.form.get("value")

        setting = db.query(SystemSetting).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.add(setting)

        db.commit()

    settings = db.query(SystemSetting).all()
    return render_template("admin_settings.html", settings=settings)


# ================================
# RUN (FOR DEBUG ONLY)
# ================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)