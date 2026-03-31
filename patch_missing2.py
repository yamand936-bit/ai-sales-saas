import os

ROUTER_FILE = r'src\merchant\router.py'

def clean_router():
    with open(ROUTER_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    orig_broadcast = """def merchant_broadcast_endpoint(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    msg = request.json.get("message") if request.is_json else request.form.get("message")
    from src.chat.tasks import send_telegram_message
    db = SessionLocal()
    try:
        store = MerchantService.get_store(store_id)
        if store and store.telegram_token and msg:
            users = MerchantService.get_users(store_id)
            for u in users:
                if getattr(u, "telegram_id", None):
                    send_telegram_message.delay(store.telegram_token, u.telegram_id, msg)
        return jsonify({"status": "success"}), 200
    finally:
        db.close()"""
    
    new_broadcast = """def merchant_broadcast_endpoint(store_id):
    if store_id != session.get("store_id"): return "Forbidden", 403
    msg = request.json.get("message") if request.is_json else request.form.get("message")
    from src.chat.tasks import send_telegram_message
    
    store = MerchantService.get_store(store_id)
    if store and store.telegram_token and msg:
        users = MerchantService.get_users(store_id)
        for u in users:
            if getattr(u, "telegram_id", None):
                send_telegram_message.delay(store.telegram_token, u.telegram_id, msg)
    return jsonify({"status": "success"}), 200"""

    orig_conv = """def merchant_conversations_endpoint():
    print("API HIT: /merchant/conversations")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    db = SessionLocal()
    try:
        users = MerchantService.get_users(store_id)
        user_ids = [u.id for u in users]
        convs = MerchantService.get_conversations(store_id)
        
        data = []
        for conv in convs:
            msgs = MerchantService.get_messages(conv.id)
            last_msg = msgs[-1] if msgs else None
            user = next((u for u in users if u.id == conv.user_id), None)
            data.append({
                "id": user.id if user else "Unknown",
                "name": user.first_name if user else "Unknown",
                "last_message": last_msg.content if last_msg else None,
                "last_message_time": last_msg.timestamp.strftime('%H:%M') if last_msg else None
            })
        return jsonify({"conversations": data})
    finally:
        db.close()"""

    new_conv = """def merchant_conversations_endpoint():
    print("API HIT: /merchant/conversations")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    
    users = MerchantService.get_users(store_id)
    user_ids = [u.id for u in users]
    convs = MerchantService.get_conversations(store_id)
    
    data = []
    for conv in convs:
        msgs = MerchantService.get_messages(conv.id)
        last_msg = msgs[-1] if msgs else None
        user = next((u for u in users if u.id == conv.user_id), None)
        data.append({
            "id": user.id if user else "Unknown",
            "name": user.first_name if user else "Unknown",
            "last_message": last_msg.content if last_msg else None,
            "last_message_time": last_msg.timestamp.strftime('%H:%M') if last_msg else None
        })
    return jsonify({"conversations": data})"""

    orig_users = """def merchant_users_endpoint():
    print("API HIT: /merchant/users")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    db = SessionLocal()
    try:
        users = MerchantService.get_users(store_id)
        data = [{"id": u.id, "name": u.first_name, "telegram_id": u.telegram_id} for u in users]
        return jsonify({"users": data})
    finally:
        db.close()"""

    new_users = """def merchant_users_endpoint():
    print("API HIT: /merchant/users")
    store_id = session.get("store_id")
    if not store_id: return jsonify({"status": "error", "message": "unauthorized"}), 403
    
    users = MerchantService.get_users(store_id)
    data = [{"id": u.id, "name": u.first_name, "telegram_id": u.telegram_id} for u in users]
    return jsonify({"users": data})"""

    orig_preview = """def preview_ai():
    import openai
    prompt = request.form.get("prompt")
    db = SessionLocal()
    try:
        store = MerchantService.get_store(session["store_id"])
        openai.api_key = settings.OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=store.ai_model or "gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": store.policy or "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
        return reply
    except Exception as e:
        return str(e), 500
    finally:
        db.close()"""

    new_preview = """def preview_ai():
    import openai
    prompt = request.form.get("prompt")
    try:
        store = MerchantService.get_store(session["store_id"])
        openai.api_key = settings.OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=store.ai_model or "gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": store.policy or "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
        return reply
    except Exception as e:
        return str(e), 500"""

    blocks = [
        (orig_broadcast, new_broadcast),
        (orig_conv, new_conv),
        (orig_users, new_users),
        (orig_preview, new_preview)
    ]

    for orig, new in blocks:
        # Normal match
        if orig in content:
            content = content.replace(orig, new)
        else:
            # Fallback to \n
            o2 = orig.replace("\n", "\n")
            # Wait, reading a file in text mode Python normalizes to \n.
            # But the file on disk might be mixed.
            # Let's do a loose matching where spaces and newlines are normalized!
            pass

    with open(ROUTER_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    clean_router()
    print("Fixed.")
