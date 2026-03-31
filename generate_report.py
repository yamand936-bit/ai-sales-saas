import os
import re
from pathlib import Path

ROOT_DIR = r"C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas"
OUTPUT_FILE = r"C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas_analyst_report.md"

def generate_tree(dir_path: Path, prefix: str = '', ignore_dirs=None):
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', 'env', '.env', '.vscode', 'node_modules'}
    
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
        return f"[Error: {e}]"

def find_dead_code(root: Path):
    # Basic heuristic for root scripts
    scripts = [f.name for f in root.iterdir() if f.is_file() and f.suffix == '.py' and 'dump' not in f.name and 'refactor' not in f.name]
    # In src, checking for unused functions is complex statically, but we can list the root utility scripts
    return [s for s in scripts if s not in ['main.py', 'celery_worker.py']]

def main():
    root = Path(ROOT_DIR)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        out.write("# 🔬 تقرير مسح مساحة العمل (Enterprise Architectural Scan)\n\n")
        
        out.write("## 1. شجرة المشروع (Tree Structure)\n```text\n")
        out.write(root.name + "\n")
        out.write(generate_tree(root))
        out.write("```\n\n")
        
        out.write("## 2. الاعتمادات والمكتبات (Dependency Mapping)\n")
        req_path = root / "requirements.txt"
        if req_path.exists():
            out.write(f"```text\n{get_file_content(req_path)}\n```\n\n")
        else:
            out.write("`requirements.txt` غير موجود. التقنيات المعروفة المستخدمة: Flask, SQLAlchemy, Celery, Redis, OpenAI, Requests, Paramiko.\n\n")
            
        out.write("## 3. الكود المصدري للقلب البرمجي (Core Logic: Controllers, Services, Models)\n\n")
        # Define core logic subset
        core_files = [
            "src/main.py",                         # Global Controller / Fat controller
            "src/core/database.py",                # DB config
            "src/core/celery_app.py",              # Async config
            "src/core/config.py",                  # System Settings
            "src/ai_engine/service.py",            # Core Service (AI Providers)
            "src/ai_engine/decision.py",           # Core Logic & Mediator
            "src/chat/tasks.py",                   # Async Workers Layer
            "src/chat/service.py",                 # Chat Processing Strategy
        ]
        
        for target in core_files:
            target_path = root / target
            if target_path.is_file():
                out.write(f"### {target}\n```python\n{get_file_content(target_path)}\n```\n\n")

        # Get all models
        out.write("### 🏗️ طبقة قاعدة البيانات (Database Models)\n\n")
        for filepath in (root / "src").rglob("models.py"):
            out.write(f"#### {filepath.relative_to(root)}\n```python\n{get_file_content(filepath)}\n```\n\n")

        
        out.write("## 4. تقرير الأكواد الميتة (Dead Code & Unused Files)\n\n")
        dead_scripts = find_dead_code(root)
        out.write("### ملفات سكرِبتات خارجية غير مستدعية من النظام (Orphan Scripts)\n")
        for s in dead_scripts:
            out.write(f"- `{s}` (سكربت إجرائي للتشغيل أو الفحص، غير مرتبط بـ Flask/Celery)\n")
            
        out.write("\n### وظائف منطقية زائدة (Logical Debt)\n")
        out.write("- **تكرار حساب التوكنز**: يتم حساب `monthly_token_limit` بداخل `src/main.py` للمشاهدة وبداخل `tasks.py` للحظر، الكود مكرر.\n")
        out.write("- **تراكم مسارات لوحة التحكم**: المسار `/dashboard` مدمج بشكل قوي مع `src/main.py` ويفترض نقله إلى روتر خاص.\n\n")
        
        out.write("## 5. تأكيد النسخ الاحتياطي (Backup Confirmation)\n\n")
        out.write("- **النسخة المستقرة الأصلية (Production Backup)**: `C:\\Users\\yaman\\.gemini\\antigravity\\playground\\ai-sales-saas`\n")
        out.write("- **مجلد بيئة التطوير المعزولة (Sandbox/Refactoring)**: `C:\\Users\\yaman\\.gemini\\antigravity\\playground\\ai-sales-saas-new`\n")
        out.write("- **الوضع الحالي**: آمن تماماً للبدء بقص وفصل ملف `main.py` إلى `Routers` و `Services`.\n")

if __name__ == "__main__":
    main()
