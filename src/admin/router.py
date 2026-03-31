import os
import datetime
import json
from flask import Blueprint, jsonify, render_template, request, redirect, flash, session
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from src.core.database import SessionLocal
from src.core.models import SystemSetting
from src.core.config import settings

from src.stores.models import Store
from src.products.models import Product
from src.users.models import User
from src.orders.models import Order
from src.chat.models import Conversation, Message, AILog
from src.utils.i18n import get_t
from src.api.middlewares import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route("/admin/login", methods=["GET", "POST"])
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

@admin_bp.route("/admin")
@admin_bp.route("/admin/")
def admin_root():
    return redirect("/admin/dashboard")

@admin_bp.route("/admin/dashboard")
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

@admin_bp.route("/admin/store/<int:store_id>/login_as")
@admin_required
def admin_login_as(store_id):
    session["role"] = "merchant"
    session["store_id"] = store_id
    return redirect("/dashboard")

@admin_bp.route("/admin/stores", methods=["GET", "POST"])
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

@admin_bp.route("/admin/settings", methods=["GET", "POST"])
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

@admin_bp.route("/admin/store/<int:store_id>", methods=["GET", "POST"])
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

@admin_bp.route("/admin/messages-order", methods=["GET"])
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

@admin_bp.route("/admin/global-token", methods=["GET"])
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

@admin_bp.route("/admin/global-live-feed", methods=["GET"])
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

@admin_bp.route("/admin/global-ai-usage", methods=["GET"])
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

@admin_bp.route("/admin/audit-logs-header", methods=["GET"])
@admin_required
def admin_audit_logs_header():
    print("API HIT: /admin/audit-logs-header")
    result = {"status": "success", "data": [{"log": "Active"}]}
    print("DB RESULT:", result)
    return jsonify(result)

@admin_bp.route("/admin/subscription-days/<int:store_id>", methods=["GET"])
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

@admin_bp.route("/admin/live_feed")
@admin_required
def admin_live_feed():
    return render_template("admin_live_feed.html")


@admin_bp.route("/admin/ai-health")
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

