import threading
import time
import requests
from src.main import app

def run_server():
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

time.sleep(2)  # Wait for server to start

urls = [
    "http://127.0.0.1:8000/admin",
    "http://127.0.0.1:8000/admin/",
    "http://127.0.0.1:8000/admin/login",
    "http://127.0.0.1:8000/admin/dashboard"
]

for u in urls:
    try:
        print(f"Testing {u}")
        start = time.time()
        res = requests.get(u, timeout=5)
        print(f"[{res.status_code}] {time.time()-start:.2f}s")
    except Exception as e:
        print(f"Failed or timeout: {e}")
