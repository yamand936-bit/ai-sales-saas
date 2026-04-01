from src.core.limiter import limiter
from flask import Blueprint, request, jsonify
from src.core.database import SessionLocal
import logging
from src.chat.tasks import process_telegram_webhook, process_whatsapp_webhook, process_instagram_webhook
import hmac
import hashlib
from src.core.config import settings

logger = logging.getLogger(__name__)
chat_bp = Blueprint('chat', __name__, url_prefix='/webhooks')

def verify_meta_signature(req):
    signature = req.headers.get("X-Hub-Signature-256")
    if not signature or not settings.META_APP_SECRET:
        return False
    payload = req.get_data()
    expected_sig = "sha256=" + hmac.new(
        settings.META_APP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature)

@chat_bp.route('/telegram/<token>', methods=['POST'])
@limiter.limit("30 per minute")
def telegram_webhook(token):
    # Process asynchronously via Celery to ensure Telegram gets immediate 200 OK
    update = request.get_json()
    if update:
        process_telegram_webhook.delay(token, update)
    return jsonify({"status": "accepted"}), 200

# --- WhatsApp Endpoints ---

@chat_bp.route('/whatsapp/<token>', methods=['GET'])
def whatsapp_verify(token):
    mode = request.args.get("hub.mode")
    verify_token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and verify_token:
        if mode == "subscribe" and verify_token == token:
            return challenge, 200
        else:
            return "Forbidden", 403
    return "Bad Request", 400

@chat_bp.route('/whatsapp/<token>', methods=['POST'])
def whatsapp_webhook(token):
    if not verify_meta_signature(request):
        return jsonify({"error": "Invalid signature"}), 403
        
    update = request.get_json()
    if update:
        process_whatsapp_webhook.delay(token, update)
    return jsonify({"status": "accepted"}), 200

# --- Instagram Endpoints ---

@chat_bp.route('/instagram/<token>', methods=['GET'])
def instagram_verify(token):
    mode = request.args.get("hub.mode")
    verify_token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and verify_token:
        if mode == "subscribe" and verify_token == token:
            return challenge, 200
        else:
            return "Forbidden", 403
    return "Bad Request", 400

@chat_bp.route('/instagram/<token>', methods=['POST'])
def instagram_webhook(token):
    if not verify_meta_signature(request):
        return jsonify({"error": "Invalid signature"}), 403
        
    update = request.get_json()
    if update:
        process_instagram_webhook.delay(token, update)
    return jsonify({"status": "accepted"}), 200
