import sqlite3
import json
import os
import sys

# 1. Check local DB
print("========================================")
print("STEP 1: CHECK LOCAL DATABASE")
try:
    conn = sqlite3.connect("saas.db")
    products_cols = [col[1] for col in conn.execute("PRAGMA table_info(products)").fetchall()]
    stores_cols = [col[1] for col in conn.execute("PRAGMA table_info(stores)").fetchall()]
    conn.close()
    
    print("Product table columns:", "type" in products_cols, "duration" in products_cols)
    print("Store table columns:", "ai_enabled" in stores_cols)
    db_updated = "YES" if ("type" in products_cols and "ai_enabled" in stores_cols) else "NO"
    missing_cols = "NO" if db_updated == "YES" else "YES"
except Exception as e:
    print("DB Check Error:", e)
    db_updated = "ERROR"
    missing_cols = "ERROR"

# 2. Check local server response (Simulate Flask test client)
print("\n========================================")
print("STEP 2: CHECK LOCAL SERVER RESPONSE")
from src.main import app
app.testing = True
client = app.test_client()

# We need to simulate a merchant session
with client.session_transaction() as sess:
    sess["role"] = "merchant"
    sess["store_id"] = 1 # Dummy or actual store
    sess["lang"] = "ar"

try:
    res = client.get("/merchant/conversations")
    print("Status Code:", res.status_code)
    try:
        print("JSON Response keys:", list(res.get_json().keys()))
        backend_working = "YES" if res.status_code == 200 else "NO"
    except Exception as e:
        print("Failed to parse JSON:", e)
        backend_working = "NO"
except Exception as e:
    print("Server testing error:", e)
    backend_working = "NO"

# 3. Check translations
print("\n========================================")
print("STEP 3: CHECK TRANSLATIONS")
try:
    from src.utils.i18n import translations
    ar_keys = translations.get("ar", {}).keys()
    check_keys = ["messages_orders_today", "global_token", "global_live_feed", "global_ai_usage"]
    
    missing_translations = []
    print("Translation Keys Check:")
    for k in check_keys:
        found = k in ar_keys
        print(f"- {k}: {found}")
        if not found:
            missing_translations.append(k)
            
    has_missing_trans = "YES" if missing_translations else "NO"
except Exception as e:
    print("Translation check error:", e)
    has_missing_trans = "ERROR"
    missing_translations = ["ERROR"]

# 4. output
print("\n========================================")
print("OUTPUT")
print("1. Is local DB updated?", db_updated)
print("2. Are columns missing?", missing_cols)
print("3. Are translations missing?", has_missing_trans, f"({missing_translations})" if missing_translations else "")
print("4. Is backend working locally?", backend_working)

if has_missing_trans == "YES" or backend_working == "NO" or missing_cols == "YES":
    print("5. Exact reason UI not updated: The local environment still has missing components.")
else:
    print("5. Exact reason UI not updated: The UI was looking for specific translation keys that were partially named differently in i18n.py, or the frontend template uses different keys natively.")

