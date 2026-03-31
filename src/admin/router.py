import os
import datetime
import json
from pydantic import ValidationError
from src.admin.schemas import StoreCreate, SystemSettingUpdate

from flask import Blueprint, jsonify, render_template, request, redirect, flash, session
from werkzeug.security import generate_password_hash

from src.core.config import settings
from src.utils.i18n import get_t
from src.api.middlewares import admin_required

from src.admin.service import AdminService

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
    stats = AdminService.get_global_stats() or {}
    return render_template("admin_dashboard.html", **stats)

@admin_bp.route("/admin/store/<int:store_id>/login_as")
@admin_required
def admin_login_as(store_id):
    session["role"] = "merchant"
    session["store_id"] = store_id
    return redirect("/dashboard")

@admin_bp.route("/admin/stores", methods=["GET", "POST"])
@admin_required
def admin_stores():
    if request.method == "POST":
        try:
            data = request.form.to_dict()
            data['plan_price'] = float(data.get('plan_price') or 0.0)
            data['monthly_token_limit'] = int(data.get('monthly_token_limit') or 100000)
            
            validated = StoreCreate(**data)
            store_data = validated.model_dump()
            store_data["password_hash"] = generate_password_hash(store_data.pop("password"))
            store_data["status"] = "active"
            
            AdminService.create_store(store_data)
            flash("Store licensed successfully", "success")
        except ValidationError as e:
            flash(f"Validation Error: {e.errors()[0]['msg']}", "error")
        except ValueError:
            flash("Validation Error: Invalid numeric field in store creation", "error")
        return redirect("/admin/stores")
        
    stores = AdminService.get_all_stores()
    return render_template("admin_stores.html", stores=stores, now=datetime.datetime.utcnow())

@admin_bp.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        try:
            data = request.form.to_dict()
            validated = SystemSettingUpdate(**data)
            
            if validated.key.endswith("_limit") and not validated.value.isdigit():
                flash(get_t(session.get("lang")).get("numeric_limit_err", "Error"), "error")
                return redirect("/admin/settings")
                
            AdminService.update_system_settings({validated.key: validated.value})
            flash(get_t(session.get("lang")).get("settings_saved_success", "Success"), "success")
        except ValidationError as e:
            flash(f"Validation error: {e.errors()[0]['msg']}", "error")
        return redirect("/admin/settings")

    settings_list = AdminService.get_system_settings()
    return render_template("admin_settings.html", settings=settings_list)

@admin_bp.route("/admin/store/<int:store_id>", methods=["GET", "POST"])
@admin_required
def admin_store_detail(store_id):
    detail = AdminService.get_store_detail(store_id)
    if not detail or not detail.get("store"):
        flash("Store not found", "error")
        return redirect("/admin/stores")
        
    store = detail.get("store")
        
    if request.method == "POST":
        action = request.form.get("action_type") or request.form.get("action")
        update_data = {}
        
        if action == "suspend":
            update_data["status"] = "suspended"
            update_data["is_active"] = False
        elif action == "activate":
            update_data["status"] = "active"
            update_data["is_active"] = True
        elif action == "quick_extend":
            extend_from = store.expires_at or datetime.datetime.utcnow()
            update_data["expires_at"] = extend_from + datetime.timedelta(days=30)
        elif action == "delete":
            AdminService.delete_store(store_id)
            flash("Store deleted", "success")
            return redirect("/admin/stores")
        else:
            update_data["name"] = request.form.get("name", store.name)
            update_data["status"] = request.form.get("status", store.status)
            update_data["is_active"] = (update_data.get("status") == 'active')
            update_data["owner_name"] = request.form.get("owner_name", store.owner_name)
            update_data["owner_phone"] = request.form.get("owner_phone", store.owner_phone)
            
            try:
                update_data["plan_price"] = float(request.form.get("plan_price") or store.plan_price)
            except ValueError:
                pass
                
            update_data["billing_cycle"] = request.form.get("billing_cycle", store.billing_cycle)
            
            try:
                update_data["monthly_token_limit"] = int(request.form.get("monthly_token_limit") or store.monthly_token_limit)
            except ValueError:
                pass
                
            update_data["payment_status"] = request.form.get("payment_status", store.payment_status)
            
            extend_days = request.form.get("extend_days")
            if extend_days and extend_days.isdigit():
                extend_from = store.expires_at or datetime.datetime.utcnow()
                update_data["expires_at"] = extend_from + datetime.timedelta(days=int(extend_days))
            
            old_tg = store.telegram_token
            new_tg = request.form.get("telegram_token", store.telegram_token)
            update_data["telegram_token"] = new_tg
            if new_tg and new_tg != old_tg:
                import requests
                webhook_url = f"https://{request.host}/webhooks/telegram/{new_tg}"
                try:
                    resp = requests.post(f"https://api.telegram.org/bot{new_tg}/setWebhook", json={"url": webhook_url}, timeout=3)
                    if resp.status_code == 200:
                        flash("Telegram webhook activated successfully! 🤖", "success")
                    else:
                        flash("Telegram token saved, but webhook failed (Domain HTTPS required).", "error")
                except Exception:
                    pass
            
            update_data["whatsapp_token"] = request.form.get("whatsapp_token", store.whatsapp_token)
            update_data["instagram_token"] = request.form.get("instagram_token", store.instagram_token)
            
            features = {
                "whatsapp": bool(request.form.get("feat_whatsapp")),
                "instagram": bool(request.form.get("feat_instagram")),
                "voice": bool(request.form.get("feat_voice")),
                "advanced_ai": bool(request.form.get("feat_advanced_ai"))
            }
            update_data["features_json"] = json.dumps(features)
            
        AdminService.update_store(store_id, update_data)
        # re-fetch store name if we updated it locally
        new_name = update_data.get("name", store.name)
        flash(f"Store {new_name} updated", "success")
        return redirect(f"/admin/store/{store_id}")
        
    features_dict = {}
    if getattr(store, 'features_json', None):
        try:
            features_dict = json.loads(store.features_json)
        except:
            pass

    return render_template("admin_store_detail.html", 
                           store=store,
                           conv_count=detail.get("conv_count", 0),
                           order_count=detail.get("order_count", 0),
                           tokens_used=detail.get("tokens_used", 0),
                           features_dict=features_dict)

@admin_bp.route("/admin/messages-order", methods=["GET"])
@admin_required
def admin_messages_order():
    print("API HIT: /admin/messages-order")
    data = AdminService.get_latest_messages()
    return jsonify({"status": "success", "data": data})

@admin_bp.route("/admin/global-token", methods=["GET"])
@admin_required
def admin_global_token():
    print("API HIT: /admin/global-token")
    stores = AdminService.get_all_stores()
    data = [{"store_id": s.id, "telegram_token": s.telegram_token} for s in stores]
    return jsonify({"status": "success", "data": data})

@admin_bp.route("/admin/global-live-feed", methods=["GET"])
@admin_required
def admin_global_live_feed():
    print("API HIT: /admin/global-live-feed")
    data = AdminService.get_latest_conversations()
    return jsonify({"status": "success", "data": data})

@admin_bp.route("/admin/global-ai-usage", methods=["GET"])
@admin_required
def admin_global_ai_usage():
    print("API HIT: /admin/global-ai-usage")
    data = AdminService.get_ai_usage()
    return jsonify({"status": "success", "data": data})

@admin_bp.route("/admin/audit-logs-header", methods=["GET"])
@admin_required
def admin_audit_logs_header():
    print("API HIT: /admin/audit-logs-header")
    return jsonify({"status": "success", "data": [{"log": "Active"}]})

@admin_bp.route("/admin/subscription-days/<int:store_id>", methods=["GET"])
@admin_required
def admin_subscription_days(store_id):
    print(f"API HIT: /admin/subscription-days/{store_id}")
    days_left = AdminService.get_subscription_days(store_id)
    return jsonify({"days_left": days_left})

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
