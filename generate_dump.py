import os
from pathlib import Path

# Paths
ROOT_DIR = r"C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas"
OUTPUT_FILE = r"C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas_technical_snapshot.md"

def generate_tree(dir_path: Path, prefix: str = '', ignore_dirs=None):
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', 'env', '.env', '.vscode'}
    
    tree_str = ""
    try:
        entries = sorted([e for e in dir_path.iterdir() if e.name not in ignore_dirs])
        for i, entry in enumerate(entries):
            connector = "├── " if i < len(entries) - 1 else "└── "
            tree_str += prefix + connector + entry.name + "\n"
            if entry.is_dir():
                extension = "│   " if i < len(entries) - 1 else "    "
                tree_str += generate_tree(entry, prefix + extension, ignore_dirs)
    except PermissionError:
        pass
    return tree_str

def get_file_content(filepath: Path) -> str:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[Error reading file: {e}]"

def main():
    root = Path(ROOT_DIR)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        out.write("# AI Sales SaaS - Technical Snapshot\n\n")
        
        # STEP 1: PROJECT STRUCTURE
        out.write("## 1. Project Directory Tree\n```text\n")
        out.write(root.name + "\n")
        out.write(generate_tree(root))
        out.write("```\n\n")
        
        # STEP 2: FILE CONTENTS
        out.write("## 2. Full Code Dump\n\n")
        targets = [
            "src/main.py",
            "src/core/",
            "src/chat/",
            "src/ai_engine/",
            "src/merchant/",
            "src/products/",
            "src/stores/",
            "src/templates/",
            "src/utils/"
        ]
        
        for target in targets:
            target_path = root / target
            if target_path.is_file():
                out.write(f"### {target}\n```python\n{get_file_content(target_path)}\n```\n\n")
            elif target_path.is_dir():
                for filepath in target_path.rglob("*"):
                    if filepath.is_file() and filepath.name not in {'.DS_Store'} and '__pycache__' not in filepath.parts:
                        ext = "python" if filepath.suffix == '.py' else "html"
                        out.write(f"### {filepath.relative_to(root)}\n```{ext}\n{get_file_content(filepath)}\n```\n\n")
        
        # STEP 3: DEPENDENCIES
        out.write("## 3. Dependencies & Configs\n")
        req_path = root / "requirements.txt"
        if req_path.exists():
            out.write(f"### requirements.txt\n```text\n{get_file_content(req_path)}\n```\n\n")
        else:
            out.write("`requirements.txt` not explicitly created in this environment.\n\n")
            
        # STEP 4: SYSTEM FLOW
        out.write("## 4. System Architecture & Flow\n\n")
        out.write("""### 1. Request Flow (Telegram -> Backend -> AI -> Response)
- **Ingestion**: Telegram sends a POST request to `/webhooks/telegram/<token>`.
- **API Router**: The Flask route (`src/chat/router.py`) immediately accepts the HTTP request and dumps the payload into a message queue (Celery) by calling `process_telegram_task.delay()`. The server responds `200 OK` to Telegram instantly.
- **Processing**: The Celery worker picks up the task.
- **Execution**: The task (`src/chat/tasks.py`) parses the user metadata, ensures the `Store` is active, and verifies the billing quota (Tokens). Then it triggers `DecisionEngine.process_message()`.
- **AI Router**: It builds the AI System Prompt by scanning DB products matching the user's intent. Then `AIEngineService` dynamically selects the cheapest non-degraded provider (OpenAI vs Gemini) from the `AIRouter`.
- **Response**: AI returns a JSON structure. The `DecisionEngine` interprets the `intent` (e.g. `checkout`), adds standard localization templates (e.g., Bank details), and publishes a socket event `publish_event("ai_reply")`. The final text is routed back to Telegram via legacy API or webhook responses natively triggered downstream.

### 2. How Celery is Triggered
- Initialized in `src/core/celery_app.py` utilizing a Redis broker (`settings.REDIS_URL`).
- Tasks are decorated via `@celery.task`.
- Tasks uniquely utilize `self.retry(exc=e, max_retries=1)` if the underlying AI system throws an `AIRetryException`, effectively isolating API limits strictly to the background process.

### 3. How Database is Used
- SQLAlchemy (Sync engine) binds to `sqlite:///./saas.db` (Configured to Postgres in VPS).
- Active Sessions (`SessionLocal`) are established locally within functions.
- Highly state-dependent. Used deeply inside `decision.py` for history tracking (`Conversation`, `Message` logic), caching system telemetry metrics (`AILog`), and user management (`User`, `Order`).

### 4. How AI Routing Works
- Encompassed within `src/ai_engine/service.py`.
- **Stateless AI Engine**: Receives `context` (which dictifies `store_id`, `history`, `is_downgraded`).
- **Semantic Cache**: Hashes the prompt using SHA-256 caching repeated short queries to Redis immediately.
- **Cost-Aware Sorting**: Assesses Provider `cost_tier`. Small prompts default to `gemini-1.5-flash` or `gpt-4o-mini` (whichever is highest active ranked). Complex "Sales" engagements or large inputs explicitly route to `gpt-4o`.
- **Circuit Breaker**: Redis instances maintain a `failure_streak:{provider}`. Degraded providers (`llen >= 3`) are skipped.
""")

        # STEP 5: KNOWN ISSUES
        out.write("## 5. Technical Issues & Architecture Debt\n\n")
        out.write("""- **Duplicated Logic**: Calculating Store total token usage occurs in both the Merchant Dashboard (inside `main.py`) and inside the Token Limiter execution in `tasks.py`/`decision.py`.
- **Tight Coupling Areas (Domain Violation)**: The AI reasoning layer (`src/ai_engine/decision.py`) is highly coupled with database IO. It simultaneously constructs Database `Order` rows, `Product` querying, and Telegram history saving rather than dispatching Intents to an abstracted `CommerceService`.
- **God Controller Anti-Pattern**: `src/main.py` is bloated. It orchestrates Flask setup, Security middlewares, Merchant Route Handlers, DB Aggregation setup, and Admin Renderings linearly without isolation.
- **Inconsistent Naming**: Mix of standard modular Blueprints (`chat_bp`) but legacy hardcoded root functions (`@app.route("/admin/ai-health")`) bundled dynamically.
- **Missing Interfaces**: No definitive Repository layer, making a full switch to AsyncDB or MongoDB highly brittle.
""")

        # STEP 6: BACKUP
        out.write("## 6. Backup Confirmation\n\n")
        out.write("""- **Primary Location**: `C:\\Users\\yaman\\.gemini\\antigravity\\playground\\ai-sales-saas` contains the verified stable codebase.
- **Refactor Sandbox**: `C:\\Users\\yaman\\.gemini\\antigravity\\playground\\ai-sales-saas-new` acts as the current active target for ongoing architectural decomposition.
- **Restore Protocol**: To restore the server, simply zip the primary `/ai-sales-saas` snapshot, push via SSH (`upload_all.py`), and execute `systemctl restart ai-sales-saas`.
""")

if __name__ == "__main__":
    main()
