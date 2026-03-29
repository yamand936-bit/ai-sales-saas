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

def merchant_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "merchant":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

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
            msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.timestamp).all()
            data.append({
                "id": conv.id,
                "user_id": conv.user_id,
                "messages": [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]
            })
        result = {"status": "success", "data": data}
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
